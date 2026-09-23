FROM python:3.12-slim
RUN pip install --no-cache-dir grpcio==1.68.1 grpcio-tools==1.68.1
WORKDIR /opt/prober
COPY protos/demo.proto /opt/prober/protos/demo.proto
RUN mkdir -p /opt/prober/gen && \
    python -m grpc_tools.protoc -I/opt/prober/protos \
      --python_out=/opt/prober/gen --grpc_python_out=/opt/prober/gen \
      /opt/prober/protos/demo.proto && \
    sed -i 's/^import demo_pb2/import demo_pb2/' /opt/prober/gen/demo_pb2_grpc.py
COPY prober_v1a.py /opt/prober/prober_v1a.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "/opt/prober/prober_v1a.py"]
