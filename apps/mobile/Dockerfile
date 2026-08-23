FROM ghcr.io/cirruslabs/flutter:stable AS build-env

# The upstream `stable` image is a moving tag. Pin the approved SDK revision
# before resolving dependencies or compiling the application.
ARG FLUTTER_VERSION=3.44.8
ARG FLUTTER_REVISION=058e0af2c2
RUN git -C /sdks/flutter fetch --depth 1 origin \
      refs/tags/${FLUTTER_VERSION}:refs/tags/${FLUTTER_VERSION} \
    && test "$(git -C /sdks/flutter rev-parse refs/tags/${FLUTTER_VERSION})" = \
      "$(git -C /sdks/flutter rev-parse ${FLUTTER_REVISION})" \
    && git -C /sdks/flutter checkout --detach ${FLUTTER_REVISION} \
    && flutter --version

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
