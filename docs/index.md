---
layout: home

hero:
  name: Carhibou
  text: Vehicle telemetry you operate yourself
  tagline: Collect GPS, OBD-II and CAN data, inspect it in the browser, and react with trusted Python hooks.
  image:
    src: /og.png
    alt: Carhibou
  actions:
    - theme: brand
      text: Install Carhibou
      link: /getting-started/installation
    - theme: alt
      text: Set up an agent
      link: /agent/agent

features:
  - title: Durable by default
    details: The vehicle agent queues readings through power and network loss; the server stores history and current state atomically.
  - title: Vehicle-specific, not guessed
    details: Declarative profiles translate known CAN frames into canonical metrics. Missing data stays missing.
  - title: Programmable on your terms
    details: Trusted Python hooks run after ingestion in a separate worker, with durable state, encrypted secrets and visible results.
---

Carhibou runs the web application, API, worker and PostgreSQL together; a standalone
Go agent runs near each vehicle.

## Start here

1. [Install the server](/getting-started/installation) with Docker Compose.
2. Add a vehicle and [enroll its agent](/user-guide/devices).
3. Configure a backup before collecting journeys you care about.

Carhibou is pre-1.0. Hardware support is described by the evidence in the
[validation ledger](/agent/diagnostics#hardware-validation-ledger), and fixture or
simulator success is never presented as physical proof.
