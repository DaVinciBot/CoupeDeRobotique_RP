import socket
import json
import time

# Configuration: Must match the Bridge script.
# By default the bridge sends to the Raspberry Pi's IP.
# If you run the bridge with a different target, set UDP_IP to that target.
UDP_IP = "192.168.0.2"
UDP_PORT = 5555

# The buffer must fit a full scan packet (~15-45 KB depending on resolution).
# 65536 is safely above any TiM5xx scan size.
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
            # Packet was truncated (buffer too small) or malformed
            print("Warning: received a malformed/truncated packet. Check BUFFER_SIZE and the bridge target IP.")
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
                # Example of accessing the dictionary format:
                if len(measurements) > 0 and measurements[0].get("dist") is not None:
                    first = measurements[0]
                    print(f"Current Scan: {len(measurements)} points. "
                          f"First -> dist {first['dist']} m, angle {first['angle']} rad, ts {first['ts']}")
                else:
                    print(f"Current Scan: {len(measurements)} points (first point is null/invalid)")
            time.sleep(0.1) # 10Hz update
    except KeyboardInterrupt:
        print("Stopped.")
