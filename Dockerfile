FROM nginx:alpine

# Copy built site assets
COPY site/ /usr/share/nginx/html/

# Custom nginx config (security headers, gzip, caching)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
