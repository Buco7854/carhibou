---
layout: home
hero:
  name: VehiNode
  text: Run your vehicle telemetry on your own server.
  tagline: Maps, history, dashboards and programmable hooks in one self-hosted application.
  actions:
    - theme: brand
      text: Install with Docker
      link: /getting-started/installation
    - theme: alt
      text: Open the user guide
      link: /user-guide/vehicles
features:
  - title: Install
    details: Start the application, worker and PostgreSQL with one Docker Compose project.
    link: /getting-started/docker
    linkText: Docker instructions
  - title: Connect an agent
    details: Enroll the lightweight Raspberry Pi agent with a short-lived token from the web interface.
    link: /agent/installation
    linkText: Agent installation
  - title: Keep it recoverable
    details: Back up PostgreSQL together with the encryption key and verify your restore procedure.
    link: /operations/backups
    linkText: Backup guide
---

## Start in three steps

1. [Install VehiNode with Docker Compose](/getting-started/installation).
2. Create your first vehicle and [enroll its agent](/user-guide/devices).
3. Configure [backups](/operations/backups) before collecting journeys you care about.

VehiNode is an open-source, pre-1.0 project. Hardware integrations are marked clearly
when they are fixture-tested but still awaiting validation on a physical vehicle.
