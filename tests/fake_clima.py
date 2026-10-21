"""Fake Modbus TCP server emulating an Innova INN-FR-B32 board behind a gateway."""

from __future__ import annotations

import asyncio
import struct


def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class FakeClima:
    """Holding registers + a Modbus TCP server (functions 03 and 06)."""

    def __init__(self, unit: int = 1) -> None:
        self.unit = unit
        self.regs: dict[int, int] = {
            0: 215,  # air 21.5
            1: 452,  # water 45.2
            2: 0,
            8: 210,
            9: 0b1001,  # boiler + EV1
            15: 900,
            104: 0b10 | (1 << 14),  # heating, H4 absent
            105: 0,
            201: 0x0100,  # reserved bit 8 set, auto, on
            202: 160,
            203: 280,
            222: 1234,
            231: 210,
            233: 3,
            209: 0,
            247: 0,
            224: 0,
            229: 350,
            267: 100,
            268: 100,
        }
        self.writes: list[tuple[int, int]] = []
        self.connections = 0
        self.drop_next = 0  # number of requests to leave unanswered
        self.late_reply = (
            False  # answer dropped requests late (after the client timeout)
        )
        self.framing = "tcp"  # or "rtu": raw RTU frames tunnelled over TCP
        self.server: asyncio.base_events.Server | None = None
        self.port = 0
        self._writers: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            for w in list(self._writers):
                w.close()
            await self.server.wait_closed()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writers.add(writer)
        self.connections += 1
        try:
            if self.framing == "rtu":
                await self._handle_rtu(reader, writer)
                return
            while True:
                header = await reader.readexactly(7)
                tid, proto, length, unit = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                if unit != self.unit:
                    resp = bytes([pdu[0] | 0x80, 11])
                else:
                    resp = self._process(pdu)
                if self.drop_next:
                    self.drop_next -= 1
                    if not self.late_reply:
                        continue
                    await asyncio.sleep(1.5)
                writer.write(struct.pack(">HHHB", tid, 0, len(resp) + 1, unit) + resp)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()

    async def _handle_rtu(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        while True:
            frame = await reader.readexactly(8)  # functions 03/06 only
            if _crc16(frame[:-2]) != struct.unpack("<H", frame[-2:])[0]:
                continue
            if frame[0] != self.unit:
                continue  # another unit on the bus: silence
            resp = bytes([self.unit]) + self._process(frame[1:-2])
            if self.drop_next:
                self.drop_next -= 1
                if not self.late_reply:
                    continue
                await asyncio.sleep(1.5)
            writer.write(resp + struct.pack("<H", _crc16(resp)))
            await writer.drain()

    def _process(self, pdu: bytes) -> bytes:
        fc = pdu[0]
        if fc == 3:
            addr, count = struct.unpack(">HH", pdu[1:5])
            if any(a not in self.regs for a in range(addr, addr + count)):
                return bytes([0x83, 2])
            vals = [self.regs[a] for a in range(addr, addr + count)]
            return bytes([3, 2 * count]) + struct.pack(f">{count}H", *vals)
        if fc == 6:
            addr, value = struct.unpack(">HH", pdu[1:5])
            if addr not in self.regs:
                return bytes([0x86, 2])
            if addr == 233 and value not in (0, 3, 5):
                return bytes([0x86, 3])
            self.regs[addr] = value
            self.writes.append((addr, value))
            if addr == 233:  # active mode follows the season
                stat = self.regs[104] & ~0b11
                self.regs[104] = stat | (0b01 if value == 5 else 0b10)
            return pdu[:5]
        return bytes([fc | 0x80, 1])
