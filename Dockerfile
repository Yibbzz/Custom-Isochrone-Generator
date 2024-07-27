FROM python:3.10.12

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV GDAL_LIBRARY_PATH /usr/lib/libgdal.so

WORKDIR /webapp

# Install system dependencies
RUN apt-get update \
    && apt-get -y install netcat-openbsd gcc postgresql \
    && apt-get -y install gdal-bin libgdal-dev \
    && apt-get clean

# Install Python dependencies
COPY requirements.txt /webapp/
RUN pip install --upgrade pip \
    # Use GDAL version that matches the libgdal-dev version installed
    && pip install GDAL==$(gdal-config --version) \
    && pip install -r requirements.txt

# Copy the current directory contents into the container
COPY . /webapp/

# Run the app
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]