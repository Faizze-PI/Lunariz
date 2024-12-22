# Use an official Node.js image
FROM node:alpine

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy your project files into the container
COPY . .

# Install the 'serve' package globally to serve the static files
RUN npm install -g serve

# Expose port 3000 (or any port you want)
EXPOSE 3000

# Command to run the app using 'serve'
CMD ["serve", "-s", ".", "-l", "3000"]
