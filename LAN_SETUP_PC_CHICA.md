# Configuración de la PC chica

Usá este `.env` en la máquina secundaria para que se conecte con la PC grande.

```env
HOST=0.0.0.0
PORT=8000
KAIROS_NODE_ID=pc-secundaria
KAIROS_NODE_BASE_URL=http://192.168.1.40:8000
KAIROS_WEB_BASE_URL=http://192.168.1.35:8000
KAIROS_PEER_URLS=http://192.168.1.35:8000
KAIROS_NODE_HEARTBEAT_TTL=15.0
```

Notas:

- `KAIROS_WEB_BASE_URL` apunta a la PC grande.
- `KAIROS_NODE_BASE_URL` apunta a esta misma PC secundaria.
- `KAIROS_PEER_URLS` lista los peers visibles desde esta PC.
- Si la IP de la PC grande cambia, actualizá ambas variables.
- Después de guardar el `.env`, reiniciá el servidor de esa PC.

Si querés que esta máquina también sea visible desde la grande, en la PC grande agregá:

```env
KAIROS_PEER_URLS=http://IP_DE_LA_PC_CHICA:8000
```
