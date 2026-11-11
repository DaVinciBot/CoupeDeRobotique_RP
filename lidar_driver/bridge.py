import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
import socket
import json
import time

# Configuration --------------------------------------------------
# TARGET_IP is the machine that should RECEIVE the scans.
# Default: the Raspberry Pi itself (see the static-IP section of the guide).
# If you want to consume the data on another machine, set TARGET_IP to
# that machine's IP, and make sure the host script binds on that same IP.
TARGET_IP = "192.168.0.2"
BIND_IP = "0.0.0.0"
UDP_PORT = 5555

class UDPBridge(Node):
    def __init__(self):
        super().__init__('lidar_udp_bridge')
        self.subscription = self.create_subscription(
            LaserScan,
            'scan',
            self.scan_callback,
            10)

        # UDP socket (bind on all interfaces, send to the target machine)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((BIND_IP, UDP_PORT))

        self.get_logger().info(f"Bridge active. Sending scans to {TARGET_IP}:{UDP_PORT}")

    def scan_callback(self, msg):
        # Map every range to a dict containing its distance, angle, and timestamp.
        # zip keeps the distance-angle pairing intact even if ranges is a generator.
        processed_data = []
        current_ts = time.time()

        for d, angle in zip(msg.ranges, msg.angles):
            # Invalid readings (0.0, inf, -0.0) become None, keeping the index intact.
            is_valid = d > 0.0 and d != float('inf') and not (str(d).split('.')[0] == '-0')
            value = d if is_valid else None

            processed_data.append({
                "dist": value,
                "angle": angle,
                "ts": current_ts
            })

        try:
            data_to_send = json.dumps(processed_data)
            self.sock.sendto(data_to_send.encode(), (TARGET_IP, UDP_PORT))
        except Exception as e:
            self.get_logger().error(f"Failed to send UDP: {e}")

def main():
    rclpy.init()
    bridge = UDPBridge()
    try:
        rclpy.spin(bridge)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()
