# Compile la simulation, lance les scenarios et trace les courbes.
# A lancer depuis n'importe quel dossier :
#   powershell -ExecutionPolicy Bypass -File firmware/teensy_motor/simulation/run.ps1
# Il faut g++ et matplotlib (pip install matplotlib).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force tmp | Out-Null

g++ -std=gnu++17 -Ifake -I../include `
    -I../lib/pid/include -I../lib/trapezoid/include `
    -I../lib/motors_driver/include -I../lib/rolling_basis/include `
    simulation.cpp ../lib/pid/src/pid.cpp ../lib/trapezoid/src/trapezoid.cpp `
    ../lib/motors_driver/src/motors_driver.cpp `
    ../lib/rolling_basis/src/rolling_basis.cpp `
    -o tmp/simulation.exe
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

foreach ($scenario in "normal", "blocage") {
    & ./tmp/simulation.exe $scenario
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    python plot.py $scenario
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
