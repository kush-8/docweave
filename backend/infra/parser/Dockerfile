FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
COPY src/docweave/text_parser.py /docweave/text_parser.py
COPY src/docweave/rag/__init__.py src/docweave/rag/contracts.py src/docweave/rag/chunking.py src/docweave/rag/parsing.py /docweave/rag/
USER 65534:65534
ENTRYPOINT ["python", "-I", "-S", "/docweave/text_parser.py"]
