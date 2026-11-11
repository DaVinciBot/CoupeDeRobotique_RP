"""Trace les courbes d'un scénario : tmp/<nom>.csv vers tmp/<nom>.png."""

import csv
import sys

import matplotlib.pyplot as plt

scenario = sys.argv[1] if len(sys.argv) > 1 else "normal"

with open(f"tmp/{scenario}.csv", encoding="utf-8") as file:
    rows = list(csv.DictReader(file))


def column(name: str) -> list[float]:
    """Renvoie une colonne du CSV sous forme de nombres."""
    return [float(row[name]) for row in rows]


t = column("t")
figure, axes = plt.subplots(5, 1, figsize=(10, 13), sharex=True)
figure.suptitle(f"Simulation de la base roulante : {scenario}")

axes[0].plot(t, column("delta_c"), label="consigne")
axes[0].plot(t, column("delta_mes"), "--", label="mesure")
axes[0].set_ylabel("Distance (cm)")

axes[1].plot(t, column("psi_c"), label="consigne")
axes[1].plot(t, column("psi_mes"), "--", label="mesure")
axes[1].set_ylabel("Angle (rad)")

axes[2].plot(t, column("v_left_c"), label="consigne")
axes[2].plot(t, column("v_left"), label="mesure", alpha=0.7)
axes[2].set_ylabel("Roue gauche (cm/s)")

axes[3].plot(t, column("v_right_c"), label="consigne")
axes[3].plot(t, column("v_right"), label="mesure", alpha=0.7)
axes[3].set_ylabel("Roue droite (cm/s)")

axes[4].plot(t, column("u_left"), label="gauche")
axes[4].plot(t, column("u_right"), label="droite")
axes[4].set_ylabel("Tension (V)")
axes[4].set_xlabel("Temps (s)")

for axis in axes:
    axis.grid(visible=True)
    axis.legend(loc="upper right")

figure.tight_layout()
figure.savefig(f"tmp/{scenario}.png", dpi=120)
print(f"Courbes dans tmp/{scenario}.png")
