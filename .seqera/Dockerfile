ARG CONNECT_CLIENT_VERSION=0.15
FROM public.cr.seqera.io/platform/connect-client:${CONNECT_CLIENT_VERSION} AS connect

FROM python:3.12-slim

ARG CONNECT_CLIENT_VERSION
LABEL io.seqera.connect.version="${CONNECT_CLIENT_VERSION}"

# The viewer is a static page; the server is Python standard library only.
COPY app /app

COPY --from=connect /usr/bin/connect-client /usr/bin/connect-client
RUN /usr/bin/connect-client --install

ENV BCM_DATA_ROOT=/workspace/data
EXPOSE $CONNECT_TOOL_PORT

ENTRYPOINT ["/usr/bin/connect-client", "--entrypoint"]
CMD ["python3", "/app/server.py"]
