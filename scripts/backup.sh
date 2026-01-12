#\!/bin/bash
# BIOTACT Backup Script
# Runs daily via cron

set -e

BACKUP_DIR="/opt/backups/biotact"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# 1. PostgreSQL backup
echo "Backing up PostgreSQL..."
docker exec biotact-postgres pg_dump -U biotact biotact 2>/dev/null | gzip > "$BACKUP_DIR/postgres_$DATE.sql.gz" || echo "PostgreSQL backup failed"

# 2. Qdrant backup (volume copy)
echo "Backing up Qdrant..."
docker run --rm -v biotact_qdrant_data_prod:/data -v "$BACKUP_DIR":/backup alpine tar czf /backup/qdrant_$DATE.tar.gz -C /data . 2>/dev/null || echo "Qdrant backup failed"

# 3. Config files backup
echo "Backing up configs..."
tar -czf "$BACKUP_DIR/configs_$DATE.tar.gz"     /opt/biotact-core-v2/.env     /opt/biotact-core-v2/prompts/     /opt/biotact-core-v2/docker-compose.prod.yml     2>/dev/null || echo "Config backup partial"

# 4. RAG documents backup
echo "Backing up RAG documents..."
tar -czf "$BACKUP_DIR/rag_docs_$DATE.tar.gz"     /opt/biotact-core-v2/data/knowledge/     2>/dev/null || echo "RAG backup partial"

# 5. Cleanup old backups
echo "Cleaning up old backups (older than $RETENTION_DAYS days)..."
find "$BACKUP_DIR" -type f -mtime +$RETENTION_DAYS -delete 2>/dev/null

# 6. Show results
echo ""
echo "Backup completed:"
ls -lh "$BACKUP_DIR"/*_$DATE* 2>/dev/null || echo "No files created"
echo ""
echo "Total backup size:"
du -sh "$BACKUP_DIR"

echo "[$(date)] Backup finished\!"
