# TransitWise Boston on Hugging Face Spaces: OpenTripPlanner and the website in one container.
# deploy/huggingface/push_space.py copies this file and the app code into the Space.

FROM eclipse-temurin:21-jre AS java

FROM python:3.12-slim-bookworm

ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=/opt/java/openjdk/bin:$PATH
COPY --from=java /opt/java/openjdk /opt/java/openjdk

RUN apt-get update \
 && apt-get install -y --no-install-recommends osmium-tool curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ARG OTP_VERSION=2.10.0
RUN curl -fsSL -o /opt/otp.jar \
    https://repo1.maven.org/maven2/org/opentripplanner/otp-shaded/${OTP_VERSION}/otp-shaded-${OTP_VERSION}.jar

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Hugging Face runs the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    OTP_JAR=/opt/otp.jar \
    OTP_DATA_DIR=/home/user/otp \
    OTP_URL=http://localhost:8080/otp/gtfs/v1 \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app
COPY --chown=user . .

# Build the routing graph now (fresh MBTA timetable + OpenStreetMap), so waking the Space only
# has to load it. Source files are deleted afterwards to keep the image small. If this step
# fails on the builder, start.sh builds the graph when the Space starts instead.
RUN python otp/setup_otp.py graph \
 && rm -rf "$OTP_DATA_DIR/download" "$OTP_DATA_DIR"/data/*.pbf "$OTP_DATA_DIR"/data/*.zip \
 || echo "graph build failed; it will be built at startup"

EXPOSE 7860
CMD ["bash", "start.sh"]
