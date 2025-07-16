FROM postgres:16

# pgvector 설치
RUN apt-get update && \
    apt-get install -y postgresql-16-pgvector && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*