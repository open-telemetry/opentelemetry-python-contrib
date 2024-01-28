FROM ubuntu:20.04

# Avoid warnings by switching to noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# This will make apt-get install without question
ARG DEBIAN_FRONTEND=noninteractive

# Install Python, pip, git, and other utilities
RUN apt-get update \
    && apt-get install -y --no-install-recommends software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3.8 python3.8-distutils \
    && apt-get install -y --no-install-recommends python3-pip python3.8-venv \
    && python3.8 -m pip install --upgrade pip \
    && apt-get install -y git \  # Added git installation here
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy your code to the container
COPY . /app

# Install any needed packages specified in requirements.txt
RUN python3.8 -m pip install -r dev-requirements.txt
#requirements.txt

# Make port 80 available to the world outside this container
EXPOSE 80

# Run app.py when the container launches
CMD ["python3.8", "pytest"]
