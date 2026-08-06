FROM ghcr.io/cirruslabs/flutter:stable AS build-env

# Enable web
RUN flutter config --enable-web

# Build the app
WORKDIR /app
COPY . .
RUN flutter pub get

# Accept API_BASE_URL as build arg
ARG API_BASE_URL
# Build the web app with the dart-define
RUN flutter build web --dart-define=API_BASE_URL=${API_BASE_URL}
RUN mv build/web/main.dart.js build/web/main_v2.dart.js
RUN sed -i 's/main.dart.js/main_v2.dart.js/g' build/web/flutter_bootstrap.js

# Serve with Nginx
FROM nginx:alpine
COPY --from=build-env /app/build/web /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
