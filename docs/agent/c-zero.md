# Citroën C-Zero profile

`citroen-c-zero-v1` covers the Mitsubishi i-MiEV / Peugeot iOn family using a safe,
declarative decoder. Initial signals reference community-documented CAN IDs `0x373`,
`0x374` and `0x412` for battery current/voltage, SOC, vehicle speed and odometer.

Every current signal is marked **experimental**. The formulas have parser fixtures but
have not been validated on this project's physical C-Zero, OBDLink SX and wiring.
Values outside declared sanity ranges are discarded.

The profile records source URLs and notes. It is an independent YAML implementation;
no third-party source code is copied. Relevant research includes
[bonybrown/iMiev Hacking Tools](https://github.com/bonybrown/iMiev-Hacking-Tools) and
[plaes/i-miev-obd2](https://github.com/plaes/i-miev-obd2). Community documentation is
evidence, not proof of correctness for every model year.

Before changing a formula, capture a reproducible drive/charge trace, corroborate the
physical measurement, update references/status, and add a fixture regression test.
