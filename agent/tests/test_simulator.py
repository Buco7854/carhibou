from agent.vehicle_agent.simulator.journey import SimulatedCZeroJourney


def test_journey_demonstrates_stationary_drive_stop_and_charge() -> None:
    journey = SimulatedCZeroJourney(100)
    start = journey.point(0)
    moving = journey.point(40)
    stopped = journey.point(75)
    charging = journey.point(95)
    assert start.speed == 0
    assert moving.speed > 0 and moving.soc < start.soc
    assert stopped.speed == 0 and not stopped.charging
    assert charging.charging and charging.battery_current > 0
