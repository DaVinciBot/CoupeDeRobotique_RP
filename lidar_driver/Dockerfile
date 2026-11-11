FROM ros:jazzy-ros-base

# Install build tools and dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    && rm -rf /var/lib/apt/lists/*

# Initialize rosdep
RUN if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then \
    rosdep init; \
    fi && rosdep update

# Create workspace
WORKDIR /work
RUN mkdir -p /work/src

# Clone and build the SICK driver
RUN git clone -b master https://github.com/SICKAG/sick_scan_xd.git /work/src/sick_scan_xd

# Build the driver with the specific Raspberry Pi optimizations
# Using -j1 and the specific flags from your instructions
RUN source /opt/ros/jazzy/setup.bash && \
    export MAKEFLAGS="-j1" && \
    colcon build \
    --packages-select sick_scan_xd \
    --executor sequential \
    --cmake-args \
    -DROS_VERSION=2 \
    -DLDMRS=0 \
    -DSCANSEGMENT_XD=0 \
    -DRASPBERRY=1 \
    --event-handlers console_direct+

# Copy the bridge script and entrypoint script into the image
COPY bridge.py /work/bridge.py
COPY entrypoint.sh /work/entrypoint.sh

# Make the entrypoint script executable
RUN chmod +x /work/entrypoint.sh

# Set up the entrypoint to run the script
# This ensures both the driver and the bridge run correctly and the container stays alive
ENTRYPOINT ["/work/entrypoint.sh"]
