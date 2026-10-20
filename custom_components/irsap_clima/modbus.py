"""Minimal asyncio Modbus TCP client (functions 03 and 06 only).

The unit is reached through an RS485 <-> Ethernet gateway running in
"Modbus TCP <-> RTU" mode, so plain Modbus TCP framing (MBAP header) is used.
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


class ModbusExceptionResponse(ModbusError):
    """The device answered with a Modbus exception."""

    def __init__(self, function: int, code: int) -> None:
        self.code = code
        super().__init__(
            f"Modbus exception {code} ({EXCEPTION_NAMES.get(code, 'unknown')}) "
            f"for function {function:#04x}"
        )


class ModbusTcpClient:
    """One persistent connection, one request at a time."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        timeout: float = 3.0,
        retries: int = 2,
        inter_request_delay: float = 0.05,
    ) -> None:
        self.host = host
        self.port = port
        self._timeout = timeout
        self._retries = retries
        self._delay = inter_request_delay
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tid = 0
        self._lock = asyncio.Lock()

    async def _connect(self) -> None:
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
        for attempt in range(self._retries + 1):
            if self._writer is None:
                await self._connect()
            assert self._reader is not None and self._writer is not None
            self._tid = (self._tid + 1) & 0xFFFF
            frame = struct.pack(">HHHB", self._tid, 0, len(pdu) + 1, unit) + pdu
            try:
                self._writer.write(frame)
                await self._writer.drain()
                while True:
                    header = await asyncio.wait_for(
                        self._reader.readexactly(7), self._timeout
                    )
                    tid, proto, length, _unit = struct.unpack(">HHHB", header)
                    body = await asyncio.wait_for(
                        self._reader.readexactly(length - 1), self._timeout
                    )
                    if tid == self._tid and proto == 0:
                        break
                    _LOGGER.debug("Discarding stale Modbus response tid=%s", tid)
            except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
                last_err = err
                await self.close()
                _LOGGER.debug("Modbus attempt %s failed: %s", attempt + 1, err)
                continue
            if self._delay:
                await asyncio.sleep(self._delay)
            if body[0] & 0x80:
                raise ModbusExceptionResponse(body[0] & 0x7F, body[1])
            return body
        raise ModbusConnectionError(
            f"No answer from unit {unit} via {self.host}:{self.port}: {last_err}"
        )

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
