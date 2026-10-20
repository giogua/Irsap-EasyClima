<p align="center">
  <img src="images/logo.png" alt="Irsap" height="72">
</p>

# Irsap EasyClima for Home Assistant

Custom integration for **Irsap CLIMA** air handling units (tested on the CLIMA 6, single-zone EasyClima) controlled over **Modbus RTU** through an RS485 ⇄ Ethernet gateway. No cloud required.

The CLIMA electronic board is an Innova **INN-FR-B32**; the register map comes from Innova document N273025C and matches the CLIMA parameters.

Each unit becomes **one device** with a thermostat entity and its sensors.

## Entities

| Platform | Entity | Notes |
|---|---|---|
| climate | the unit | off / heat / cool / heat-cool (automatic season), set point, fan program (auto, silent, night, max) as fan modes, current action |
| sensor | Air temperature, Water temperature (H2), Fan speed (rpm) | |
| sensor | Water temperature H4 | 4-pipe units only, disabled by default |
| sensor | Effective set point, Fan operating hours, Alarms | diagnostic |
| sensor | Modbus registers | diagnostic, disabled by default: raw values of all polled registers |
| binary_sensor | Heat request (BOILER), Cooling request (CHILLER), Water valve, Alarm, Filter maintenance | |
| binary_sensor | Antifreeze, Water temperature not suitable | diagnostic |
| switch | Keyboard lock | config, disabled by default |

Entity names are translated (English, Italian).

## Hardware

- The Modbus supervisor **replaces the CNT wall panel**: per the CLIMA manual the RS485 port is used either by the panel (ASCII protocol) or by a supervisor (Modbus RTU), not both.
- Move the jumper on the CLIMA board from **ASCII** to **RTU**.
- Connect the board terminals A/B to the gateway RS485 A/B (shielded twisted pair). Do not power the gateway from the board's panel supply.
- Without the CNT panel, the regulation uses the **AIR probe** on the return air (connector H2 on the board): it must be connected.
- Gateway (tested with a Waveshare *RS485 TO POE ETH (B)*): protocol **Modbus TCP to RTU**, **9600 8N1**, TCP server. Note the TCP port shown by the gateway (Waveshare default 4196).

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → `https://github.com/giogua/Irsap-EasyClima`, category **Integration**.
2. Install **Irsap EasyClima (CLIMA)** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → Irsap EasyClima*, then enter the gateway IP and port and the Modbus unit id (default 1).

## Register map (Innova INN-FR-B32)

| Reg. | Access | Meaning |
|---|---|---|
| 0 | R | air temperature, ×0.1 °C |
| 1 / 2 | R | water temperature H2 / H4, ×0.1 °C |
| 8 | R | effective set point, ×0.1 °C |
| 9 | R | outputs: bit0 EV1, bit1 EV2, bit2 CHILLER, bit3 BOILER |
| 15 | R | requested fan speed, rpm |
| 104 | R | status: bit0 cooling, bit1 heating, bit8 antifreeze, bit9 alarm, bit11 standby, bit13/14 H2/H4 probe absent… |
| 105 | R | alarms: bit0 com, bit1 AIR probe, bit2 H4, bit3 harmful water, bit4 H2, bit7 motor, bit8 GRID, bit10 filter… |
| 201 | R/W | bit0-1 program (0 auto, 1 silent, 2 night, 3 max), bit4 keyboard lock, bit7 standby; bits 8-15 reserved |
| 202 / 203 | R/W | set point limits, ×0.1 °C |
| 222 | R/W | fan working hours |
| 231 | R/W | set point, ×0.1 °C |
| 233 | R/W | season: 0 auto, 3 winter, 5 summer |

Register 201 is always updated with a read-modify-write, so the reserved bits and the bits not being changed are preserved. Configuration registers (fan speeds, water thresholds, address) are never written.

## Development

```bash
pip install pytest pytest-asyncio
pytest tests/test_api.py               # client against a simulated unit (tests/fake_clima.py)

pip install pytest-homeassistant-custom-component
pytest -o asyncio_mode=auto tests/ha   # end-to-end tests inside Home Assistant
```

## Disclaimer

This is an unofficial, community project. It is not affiliated with or endorsed by Irsap S.p.A. or Innova S.r.l. The Irsap name and logo are trademarks of their owner and are used only to identify the supported devices.
