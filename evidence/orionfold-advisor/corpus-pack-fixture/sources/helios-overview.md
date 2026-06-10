# Helios Grid Analytics — Platform Overview

Helios Grid Analytics is a synthetic fixture document for the Orionfold Advisor
corpus-pack swap gate. It describes a fictional customer product so the swap
demonstration never touches real customer data.

## What the platform does

Helios Grid Analytics ingests battery telemetry from utility-scale storage
sites and produces dispatch recommendations. The platform's three modules are
Telemetry Intake, Degradation Modeling, and Dispatch Advisor. Degradation
Modeling estimates cell state-of-health from charge-cycle curvature, and the
Dispatch Advisor schedules charge/discharge windows against day-ahead price
forecasts.

## Key facts

- The supported telemetry cadence is one sample every 4 seconds per string.
- Degradation Modeling retrains weekly on a rolling 90-day window.
- The Dispatch Advisor publishes its schedule at 17:30 local time daily.
- Helios supports NMC and LFP chemistries; flow batteries are out of scope.

## Positioning

Helios sells to independent power producers who own 10 MWh to 400 MWh of
storage and want vendor-neutral dispatch logic that runs inside their own
network boundary.
