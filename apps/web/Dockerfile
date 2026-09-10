# ---------- dev ----------
FROM node:22-alpine AS dev
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ---------- build ----------
FROM node:22-alpine AS build
WORKDIR /app

# Vite inlines VITE_* values into the bundle at build time, so they have to be
# present here — setting them on the running container does nothing. Defaults
# are relative paths, which is what we want behind a single nginx.
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_CCM_DASHBOARD_URL=/ccm/
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_CCM_DASHBOARD_URL=$VITE_CCM_DASHBOARD_URL

COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# ---------- prod ----------
FROM nginx:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
