FROM python:3.11-slim
RUN useradd --create-home --uid 1000 user
USER user
WORKDIR /home/user/app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --chown=user hf_storage.py space_server.py ./
COPY --chown=user site/ ./site/
EXPOSE 7860
CMD ["python", "-B", "space_server.py"]
