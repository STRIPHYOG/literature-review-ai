FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy application code
COPY . .

# Expose port
EXPOSE 3000

# Default command (overridden by docker-compose)
CMD ["npm", "run", "dev"]
