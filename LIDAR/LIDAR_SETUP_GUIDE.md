# LiDAR Setup & Integration Guide (SICK TiM561 + Raspberry Pi)

This guide provides a streamlined workflow for deploying a SICK LiDAR driver on a Raspberry Pi using Docker. By following this guide, you will have a containerized ROS 2 environment that broadcasts LiDAR data over UDP, allowing the host machine to consume the data easily.

---
## General Idea of the Setup
The system is a **Docker container**, the image has to be created once by the DockerFile, then you can just start the container and it should begin outputing by itself without further interaction. (hopefully lol)

**On build it:**
1. downloads the drivers and ROS2 from source, along with the dependencies, then builds it all with the right flags
2. copies the bridge.py script, used to broadcast the measurement data on UDP port 5555, to HOME~/work/bridge.py. it does it alongside entrypoint.sh (copied to HOME~/work/entrypoint.sh), that is the script the container calls at every start

**Then on every start of the container, the entrypoint.sh script tells it to:**
1. wait up to 30 seconds for the lidar driver to start up
2. then run the bridge.py script until container stopped, sending the data the USP port 5555 for use from Raspberry PI OS

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Networking (Static IP)](#networking-static-ip)
3. [Docker Deployment](#docker-deployment)
4. [The Data Pipeline](#the-data-pipeline)
5. [Example Use Case (Host Script)](#example-use-case-host-script)
6. [Troubleshooting & Known Issues](#troubleshooting--known-issues)

---

## Prerequisites
*   **Hardware:** Raspberry Pi (Pi 4 or 5 recommended) and a SICK TiM561 LiDAR.
*   **OS:** Raspberry Pi OS 64-bit (Lite or Desktop).
*   **Network:** The Pi and the LiDAR must be on the same subnet. (Tested with lidar connected directly to the pi's ethernet port)

## Networking (Static IP)
To ensure consistent communication, the Raspberry Pi requires a static IP address on the `eth0` connection.

1.  **Identify connection:** Run `nmcli connection show`. Look for "Wired connection 1" or "eth0".
2.  **Set Static IP:** Replace `"Wired connection 1"` with `"eth0"` (or your connection name if different):
    ```bash
    sudo nmcli connection modify "eth0" \
        ipv4.addresses 192.168.0.2/24 \
        ipv4.method manual \
        ipv4.gateway "" \
        ipv6.method ignore
    ```
3.  **Restart connection:**
    ```bash
    sudo nmcli connection up "eth0"
    ```
4.  **Verify:** Run `ip -br addr` to ensure `eth0` is `UP` at `192.168.0.2`.
5.  **Ping the LiDAR:** Ensure you can reach the LiDAR at its IP (e.g., `192.168.0.1`):
    ```bash
    ping 192.168.0.1
    ```
    *   **Note:** Ensure the LiDAR's actual IP address matches the one used in the `entrypoint.sh` script and this guide before proceeding.

## Docker Deployment
We use a Docker container to isolate the ROS 2 environment and all build dependencies. This avoids "dependency hell" on the host OS.

### 0. Install Docker (If not already installed)
If you don't have Docker installed, run the following commands:
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable --now docker
```
*Note: You may need to restart your Pi if the system updates require it.*

### 1. Build the Image
Navigate to the directory containing the `Dockerfile` and run:
```bash
docker build -t lidar-driver .
```
*Note: This takes a few minutes. The build is memory-heavy on a Pi — make sure you have a decent swap file (≥ 4 GB) and enough free RAM, or the build will fail.*

### 2. Run the Container
Run the container using the `host` network mode so it can communicate with the LiDAR and broadcast to your host:
```bash
docker run -it --rm --network host lidar-driver
```
The container will automatically:
1.  Start the `sick_scan_xd` driver.
2.  Wait for the `/scan` topic to be published.
3.  Start the `bridge.py` script, which broadcasts a JSON list of scan points to the Raspberry Pi's IP (`192.168.0.2:5555`).

*   **Tip:** If the container starts but you don't see data, check the logs by running `docker logs <container_id>` (though the `--rm` flag makes this tricky, you can check the output in your current terminal).

## The Data Pipeline
The system works in three stages:
1.  **Driver:** The `sick_scan_xd` driver communicates with the LiDAR via Ethernet.
2.  **Bridge (Inside Container):** A Python script (`bridge.py`) subscribes to the ROS 2 `/scan` topic and converts each scan into a JSON list of points (distance, angle, timestamp), sending it over UDP port 5555 to the Raspberry Pi's IP (`192.168.0.2`).
3.  **Consumer (Your Code):** Your application listens on UDP port 5555 (on the Pi, or on any other machine on the same network by changing `TARGET_IP`) to receive real-time data.

## Example Use Case (Host Script)
Run this on the Raspberry Pi (or any machine on the same network) to verify data is flowing. It binds on `192.168.0.2:5555`, the default bridge target.

```python
import socket
import json
import time

# Configuration: must match the bridge's TARGET_IP
UDP_IP = "192.168.0.2"
UDP_PORT = 5555

# A full scan packet is ~15-45 KB; 65536 is safely above any TiM5xx size.
BUFFER_SIZE = 65536

class LidarClient:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((UDP_IP, UDP_PORT))
        self.sock.setblocking(False) # Non-blocking so it doesn't freeze your code
        self.last_measurement = []
        print(f"Listening for LiDAR data on {UDP_IP}:{UDP_PORT}...")

    def update_data(self):
        """
        Checks the socket for any new data.
        Returns the new array if found, otherwise returns the last known array.
        """
        try:
            data, addr = self.sock.recvfrom(BUFFER_SIZE)
            self.last_measurement = json.loads(data.decode())
            return self.last_measurement
        except BlockingIOError:
            # No data received in this millisecond, return last known
            return self.last_measurement
        except json.JSONDecodeError:
            print("Warning: malformed/truncated packet. Check BUFFER_SIZE and the bridge TARGET_IP.")
            return self.last_measurement
        except Exception as e:
            print(f"Error: {e}")
            return self.last_measurement

    def get_one_full_measurement_array(self):
        """
        This is your requested function.
        Call it whenever you need the most recent array.
        """
        return self.update_data()

# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    client = LidarClient()
    try:
        while True:
            measurements = client.get_one_full_measurement_array()
            if measurements:
                if len(measurements) > 0 and measurements[0].get("dist") is not None:
                    first = measurements[0]
                    print(f"Current Scan: {len(measurements)} points. "
                          f"First -> dist {first['dist']} m, angle {first['angle']} rad, ts {first['ts']}")
                else:
                    print(f"Current Scan: {len(measurements)} points (first point is null/invalid)")
            time.sleep(0.1) # 10Hz update
    except KeyboardInterrupt:
        print("Stopped.")
```

## Troubleshooting & Known Issues
*   **Build Failures:** If the `docker build` fails, ensure you have enough swap space (recommended 4GB).
*   **Pi 5 Errors:** Some users have reported runtime errors with specific scanners (e.g., MRS 6xxx) on the Raspberry Pi 5. Check the `SICKAG/sick_scan_xd` GitHub issues for specific workarounds.
*   **No Data:** Verify that the Pi can `ping` the LiDAR and that the Static IP is correctly assigned to `eth0`.

---

## Expected Output & Consumption
Once the container is running, it acts as a UDP server. You can consume the LiDAR data from any script running on the host (or any machine on the same network) by listening to the specified port.

### How to listen:
*   **IP:** `192.168.0.2` (the Raspberry Pi's static IP, which is the bridge's default `TARGET_IP`)
*   **UDP Port:** `5555`

*   You can bind on `192.168.0.2` from the Pi itself or from any other machine on the same network. To change the target, edit `TARGET_IP` in `bridge.py` and point the host script's `UDP_IP` at the same address.

### Data Structure:
The bridge sends a JSON-encoded list of objects. Each object represents one "point" in the scan.
**Example Packet:**
```json
[
  {"dist": 1.25, "angle": 0.01, "ts": 1735689600.123},
  {"dist": 2.40, "angle": 0.02, "ts": 1735689600.123},
  {"dist": null, "angle": 0.03, "ts": 1735689600.123}
]
```
*   **`dist`**: The distance to the object in meters. A value of `null` indicates an invalid reading (e.g., out of range or noise).
*   **`angle`**: The rotation angle of that specific distance, in radians, as published by the driver. For the TiM561 the values run from **−2.356 rad (−135°) to +2.356 rad (+135°)**, in steps of about **0.0058 rad (0.333°)**.
    *   **0.0 rad** corresponds to the "front" of the sensor (the sensor's physical 90° axis), and the physical device sweep of 270° (−45° to +225°) maps onto this ±135° range.
    *   To convert to degrees: `degrees = radians * (180 / math.pi)`.
    *   The physical left/right direction of a positive/negative angle depends on the sensor's mounting; verify it once with a known object, then the convention is fixed for the whole setup.
*   **`ts`**: The Unix timestamp of when the scan was captured by the driver.

By preserving the `angle` and `ts` in every object, you can accurately map points in 3D space and handle multi-sensor fusion or time-series analysis without worrying about index shifting.
