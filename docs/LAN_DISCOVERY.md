# Descubrimiento y acceso a Kairos

Kairos descubre automáticamente otros nodos de su mismo clúster en la red local. Cada nodo anuncia por multicast UDP su identificador y puerto; la dirección se toma del paquete recibido, por lo que un cambio de IP por DHCP no exige editar configuración.

## Uso local

- `KAIROS_LAN_DISCOVERY=true` viene activado por defecto.
- `KAIROS_PEER_URLS` y `KAIROS_NODE_BASE_URL` son overrides opcionales para redes que bloquean multicast.
- El tráfico de descubrimiento usa `239.255.42.99:42429` y no atraviesa routers.
- La aplicación HTTP sigue usando el puerto `8000` salvo que se configure otro.

El descubrimiento elimina la configuración manual entre nodos, pero no puede crear por sí solo un nombre que todos los navegadores resuelvan. Para un enlace estable dentro de una red se necesita DNS local o mDNS; para publicar el producto en Internet se necesita un dominio HTTPS y un servicio de registro/autenticación. El multicast queda exclusivamente como mecanismo LAN.

## Servicio persistente

En Windows:

```powershell
.\scripts\kairos-windows-service.ps1 -Action Install
```

En Linux:

```bash
./scripts/install-linux-user-service.sh
```

La unidad de systemd tiene reinicio automático y un apagado gradual máximo de ocho segundos.
