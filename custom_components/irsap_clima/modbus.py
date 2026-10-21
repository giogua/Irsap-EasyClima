"""Minimal asyncio Modbus client over TCP (functions 03 and 06 only).

The unit is reached through an RS485 <-> Ethernet gateway, either in
"Modbus TCP <-> RTU" mode (framing "tcp": MBAP header, the gateway converts)
or in transparent mode (framing "rtu": raw RTU frames with CRC are tunnelled
over the TCP connection and the gateway only forwards bytes).
The connection is kept open and is closed only on socket errors: cheap
gateways often accept a single client and refuse new connections for minutes
after one is closed.
Implemented here instead of depending on pymodbus, whose API changes between
the versions pinned by different Home Assistant releases.
"""

from __future__ import annotations

import asyncio
import logging
import struct

_LOGGER = logging.getLogger(__name__)

FC_READ_HOLDING = 0x03
FC_WRITE_SINGLE = 0x06

EXCEPTION_NAMES = {
    1: "illegal function",
    2: "illegal data address",
    3: "illegal data value",
    4: "slave device failure",
    10: "gateway path unavailable",
    11: "gateway target device failed to respond",
}


class ModbusError(Exception):
    """Communication error."""


class ModbusConnectionError(ModbusError):
    """The gateway cannot be reached or did not answer."""


class ModbusTimeoutError(ModbusError):
    """Connected to the gateway, but no (valid) answer from the unit."""


class ModbusExceptionResponse(ModbusError):
    """The device answered with a Modbus exception."""

    def __init__(self, function: int, code: int) -> None:
        self.code = code
        super().__init__(
            f"Modbus exception {code} ({EXCEPTION_NAMES.get(code, 'unknown')}) "
            f"for function {function:#04x}"
        )


FRAMING_TCP = "tcp"
FRAMING_RTU = "rtu"


def crc16(data: bytes) -> int:
    """Modbus RTU CRC16."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class ModbusTcpClient:
    """One persistent connection, one request at a time."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        timeout: float = 3.0,
        retries: int = 2,
        inter_request_delay: float = 0.05,
        framing: str = FRAMING_TCP,
    ) -> None:
        self.host = host
        self.port = port
        self.framing = framing
        self._timeout = timeout
        self._retries = retries
        self._delay = inter_request_delay
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tid = 0
        self._lock = asyncio.Lock()
        self._dirty = False  # a request timed out: late bytes may be pending

    async def _drain(self) -> None:
        """Discard bytes left over by a request that timed out.

        RTU frames carry no transaction id, so a late answer could be taken
        for the answer to the next request: wait longer for it to arrive.
        """
        assert self._reader is not None
        quiet = self._timeout if self.framing == FRAMING_RTU else 0.2
        while True:
            try:
                data = await asyncio.wait_for(self._reader.read(512), quiet)
            except TimeoutError:
                break
            if not data:  # connection closed by the gateway
                await self.close()
                break
            _LOGGER.debug("Discarded %s stale bytes", len(data))
        self._dirty = False

    async def _connect(self) -> None:
        _LOGGER.debug("Connecting to %s:%s", self.host, self.port)
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self._timeout
            )
        except (OSError, TimeoutError) as err:
            raise ModbusConnectionError(
                f"Cannot connect to {self.host}:{self.port}: {err}"
            ) from err

    async def close(self) -> None:
        """Close the connection."""
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
        self._reader = self._writer = None

    async def _transaction(self, unit: int, pdu: bytes) -> bytes:
        """Send a PDU and return the response PDU (without unit id)."""
        last_err: Exception | None = None
        connected = False
        for attempt in range(self._retries + 1):
            if self._writer is not None and self._dirty:
                await self._drain()
            if self._writer is None:
                await self._connect()
            connected = True
            assert self._reader is not None and self._writer is not None
            try:
                if self.framing == FRAMING_RTU:
                    body = await self._exchange_rtu(unit, pdu)
                else:
                    body = await self._exchange_tcp(unit, pdu)
            except TimeoutError as err:
                # The gateway is still connected but the unit did not answer
                # (or answered late).  Keep the socket: some gateways accept a
                # single client and refuse new connections for minutes after
                # one is closed.  A late answer is discarded by its tid.
                last_err = err
                self._dirty = True
                _LOGGER.debug(
                    "Modbus attempt %s timed out (unit %s)", attempt + 1, unit
                )
                continue
            except (OSError, asyncio.IncompleteReadError) as err:
                last_err = err
                await self.close()
                _LOGGER.debug("Modbus attempt %s failed: %r", attempt + 1, err)
                continue
            if self._delay:
                await asyncio.sleep(self._delay)
            if body[0] & 0x80:
                raise ModbusExceptionResponse(body[0] & 0x7F, body[1])
            return body
        error = ModbusTimeoutError if connected else ModbusConnectionError
        raise error(
            f"No answer from unit {unit} via {self.host}:{self.port}: "
            f"{type(last_err).__name__} {last_err}"
        )

    async def _exchange_tcp(self, unit: int, pdu: bytes) -> bytes:
        assert self._reader is not None and self._writer is not None
        self._tid = (self._tid + 1) & 0xFFFF
        frame = struct.pack(">HHHB", self._tid, 0, len(pdu) + 1, unit) + pdu
        self._writer.write(frame)
        await self._writer.drain()
        while True:
            header = await asyncio.wait_for(self._reader.readexactly(7), self._timeout)
            tid, proto, length, _unit = struct.unpack(">HHHB", header)
            body = await asyncio.wait_for(
                self._reader.readexactly(length - 1), self._timeout
            )
            if tid == self._tid and proto == 0:
                return body
            _LOGGER.debug("Discarding stale Modbus response tid=%s", tid)

    async def _exchange_rtu(self, unit: int, pdu: bytes) -> bytes:
        """Send a raw RTU frame and read the answer, validated by its CRC."""
        assert self._reader is not None and self._writer is not None
        frame = bytes([unit]) + pdu
        self._writer.write(frame + struct.pack("<H", crc16(frame)))
        await self._writer.drain()

        async def read(n: int) -> bytes:
            return await asyncio.wait_for(self._reader.readexactly(n), self._timeout)

        head = await read(2)
        if head[1] & 0x80:
            rest = await read(3)  # exception code + CRC
        elif head[1] == FC_READ_HOLDING:
            count = await read(1)
            rest = count + await read(count[0] + 2)
        else:
            rest = await read(6)  # write echo: address, value, CRC
        answer = head + rest
        if crc16(answer[:-2]) != struct.unpack("<H", answer[-2:])[0] or head[0] != unit:
            # Garbage or a late answer to an earlier request: resynchronise.
            raise TimeoutError(f"Invalid RTU frame {answer.hex(' ')}")
        return answer[1:-2]

    async def read_holding(self, unit: int, address: int, count: int = 1) -> list[int]:
        """Read holding registers (function 03)."""
        async with self._lock:
            body = await self._transaction(
                unit, struct.pack(">BHH", FC_READ_HOLDING, address, count)
            )
        if body[0] != FC_READ_HOLDING or body[1] != 2 * count:
            raise ModbusError(f"Malformed response to read {address}: {body.hex()}")
        return list(struct.unpack(f">{count}H", body[2 : 2 + 2 * count]))

    async def write_register(self, unit: int, address: int, value: int) -> None:
        """Write a single register (function 06)."""
        async with self._lock:
            body = await self._transaction(
                unit, struct.pack(">BHH", FC_WRITE_SINGLE, address, value & 0xFFFF)
            )
        if body[:5] != struct.pack(">BHH", FC_WRITE_SINGLE, address, value & 0xFFFF):
            raise ModbusError(f"Unexpected echo to write {address}: {body.hex()}")
