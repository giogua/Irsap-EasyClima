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
| sensor | Air temperature, Water temperature (H2), Fan speed (%) | |
| sensor | Water temperature H4 | 4-pipe units only, disabled by default |
| sensor | Effective set point, Fan operating hours, Alarms | diagnostic |
| sensor | Modbus registers | diagnostic, disabled by default: raw values of all polled registers |
| binary_sensor | Heat request (BOILER), Cooling request (CHILLER), Water valve, Alarm, Filter maintenance | |
| binary_sensor | Antifreeze, Water temperature not suitable | diagnostic |
| select | Season (winter / summer / automatic) | config: changes the season without switching the unit on |
| switch | Keyboard lock | config, disabled by default |

Entity names are translated (English, Italian).

## Hardware

- The Modbus supervisor **replaces the CNT wall panel**: per the CLIMA manual the RS485 port is used either by the panel (ASCII protocol) or by a supervisor (Modbus RTU), not both.
- Move the jumper on the CLIMA board from **ASCII** to **RTU**.
- Connect the board terminals A/B to the gateway RS485 A/B (shielded twisted pair). Do not power the gateway from the board's panel supply.
- Without the CNT panel, the regulation uses the **AIR probe** on the return air (connector H2 on the board): it must be connected.
- Gateway (tested with a Waveshare *RS485 TO POE ETH (B)*): **9600 8N1**, TCP server; note the TCP port (Waveshare default 4196). Two gateway protocols are supported, chosen in the integration setup:
  - **Modbus RTU over TCP** (recommended for Waveshare): gateway protocol **None** (transparent). The integration sends raw RTU frames with CRC; the gateway only forwards bytes.
  - **Modbus TCP**: gateway protocol **Modbus TCP to RTU**. On the Waveshare (firmware V1.452) this mode was seen to reset the connection and then refuse new ones for minutes.
- These gateways accept one client at a time: close Vircom or any other tool connected to the same port while Home Assistant is running.

## Fan control

Without the CNT panel the integration acts as the supervisor, like the Irsap EasyClima multizone controller:

- the **unit** decides *when* the fan runs (thermal demand measured by the AIR probe, periodic air sampling);
- the **integration** decides *how fast* it runs during demand, writing registers 267/268 at every refresh.

The fan modes of the thermostat are the unit programs (stored on the unit, register 201):

| Fan mode | Speed |
|---|---|
| auto | proportional to the distance from the set point: minimum (default 20 %) at the set point, maximum (default 70 %) 2 °C away; changes by at most 5 % per refresh |
| silent | fixed, default 35 % |
| night | fixed, default 20 % |
| max | fixed, default 100 % |

All speeds are configurable in the integration options. When the unit is switched off the speed is set to 20 %, as the EasyClima controller does.

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
| 15 | R | fan speed, % (0 when stopped) |
| 104 | R | status: bit0 cooling, bit1 heating, bit8 antifreeze, bit9 alarm, bit11 standby, bit13/14 H2/H4 probe absent… |
| 105 | R | alarms: bit0 com, bit1 AIR probe, bit2 H4, bit3 harmful water, bit4 H2, bit7 motor, bit8 GRID, bit10 filter… |
| 201 | R/W | bit0-1 program (0 auto, 1 silent, 2 night, 3 max), bit4 keyboard lock, bit7 standby; bits 8-15 reserved |
| 202 / 203 | R/W | set point limits, ×0.1 °C |
| 222 | R/W | fan working hours |
| 231 | R/W | set point, ×0.1 °C |
| 233 | R/W | season: 0 auto, 3 winter, 5 summer |
| 224 | R/W | 0 = fan speed from the supervisor; with other values the unit stays in standby (written 0 when switching on) |
| 267 / 268 | R/W | fan speed % during thermal demand, written by the supervisor (both with the same value) |

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
