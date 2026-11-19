# Builds the simulation, runs the scenarios and plots the curves.
# Can be run from any folder:
#   powershell -ExecutionPolicy Bypass -File firmware/teensy_motor/simulation/run.ps1
# Needs g++ and matplotlib (pip install matplotlib).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force tmp | Out-Null

g++ -std=gnu++17 -Wall `
    -I../lib/pid/include -I../lib/trapezoid/include -I../lib/motion_control/include `
    simulation.cpp ../lib/pid/src/pid.cpp ../lib/trapezoid/src/trapezoid.cpp `
    ../lib/motion_control/src/motion_controller.cpp `
    -o tmp/simulation.exe
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

foreach ($scenario in "normal", "blocage", "recalage") {
    & ./tmp/simulation.exe $scenario
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    python plot.py $scenario
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
