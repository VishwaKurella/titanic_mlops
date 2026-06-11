FROM nginx:1.27-alpine

# Remove the default nginx config and html
RUN rm /etc/nginx/conf.d/default.conf
RUN rm -rf /usr/share/nginx/html/*

# Copy our nginx config
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Copy built static files from builder
COPY public/ /usr/share/nginx/html/

# ── Security hardening ─────────────────────────────────────────────────────────
# nginx master process must run as root to bind port 80, but worker processes
# run as the 'nginx' user (already set in the base image).
# We can go further and run on an unprivileged port — change nginx.conf to
# listen on 3000 and use USER nginx here if you want full non-root.

# Remove server version header (minor info leak hardening)
RUN sed -i 's/^.*server_tokens.*$/    server_tokens off;/' /etc/nginx/nginx.conf || true

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]