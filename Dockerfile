# Use official Python image
FROM python:3.10

# Set working directory explicitly
WORKDIR /app

# Copy requirements.txt first
COPY requirements.txt /app/

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the application
COPY . /app/

# Expose Flask's port
EXPOSE 5000

# Start the Flask app with Gunicorn
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "main:app"]
