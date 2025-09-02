FROM python:3.11

# Remove existing ChromeDriver
RUN rm -rf /root/.wdm/drivers/chromedriver/linux64/

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    unzip \
    curl \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpam0g \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    --no-install-recommends

    
# --- Install Chrome and ChromeDriver 124.0.6367.207 ---

# Download and install Google Chrome
RUN wget --no-verbose -O /tmp/chrome.deb https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/124.0.6367.207/linux64/chrome-linux64.zip \
    && unzip /tmp/chrome.deb -d /opt/ \
    && rm /tmp/chrome.deb \
    && ln -s /opt/chrome-linux64/chrome /usr/bin/google-chrome-stable

# Download and install ChromeDriver
RUN wget --no-verbose -O /tmp/chromedriver.zip https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/124.0.6367.207/linux64/chromedriver-linux64.zip \
    && unzip /tmp/chromedriver.zip -d /usr/bin/ \
    && rm /tmp/chromedriver.zip \
    && chmod +x /usr/bin/chromedriver-linux64/chromedriver

# Copy all Python modules and requirements.txt to /app
COPY *.py /app/
# Python dependencies
COPY requirements.txt /app/ 
WORKDIR /app


# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Start Flask app on port 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app", "--capture-output"]