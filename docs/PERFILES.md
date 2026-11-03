# Perfil del personal

Mi perfil está disponible en el menú y al pulsar el avatar. Todos los roles pueden editar su nombre, reemplazar o quitar su foto y cambiar la contraseña mediante su clave actual. El chofer también puede corregir su número de licencia.

Administración puede corregir nombre, correo de acceso y licencia de otras cuentas desde Gestión de usuarios. Esa edición invalida su sesión e inutiliza los códigos de recuperación anteriores. La edición personal del correo se canaliza por administración.

Las fotografías aceptan JPG, PNG y WebP estáticos de hasta 2 MB y 4096 × 4096 píxeles. Se recortan a 256 × 256, se vuelven a codificar como PNG y se eliminan sus metadatos. Se almacenan en fotos_perfil y su lectura requiere la sesión del dueño. El respaldo SQL existente incluye estas imágenes.

El cambio de contraseña revoca el acceso anterior y exige un nuevo ingreso. Se conserva la política de sesión única y vencimientos.

## Actualización del VPS

Ejecutar dentro de la sesión SSH del usuario formopack.

```bash
cd ~/formopack-app &&
sudo /usr/local/sbin/formopack-backup &&
git pull --ff-only &&
sudo mariadb formopack_db < scripts/migrations/013_perfiles.sql &&
sudo systemctl restart formopack &&
systemctl is-active formopack
```

La migración 013 es aditiva y repetible. Se aplica con la cuenta administrativa local de MariaDB porque la cuenta de ejecución de la aplicación tiene permisos limitados. Este comando aplica únicamente el archivo 013. Si posteriormente se usa MigrationManager, podrá repetir su CREATE TABLE IF NOT EXISTS sin cambiar las fotos existentes. Aplicarla antes de reiniciar. Abrir Mi perfil, guardar datos y verificar la foto en el encabezado.
