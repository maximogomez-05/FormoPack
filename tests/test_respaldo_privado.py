"""El respaldo incluye las evidencias nuevas y anteriores sin leer datos reales."""

import io
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest


def test_respaldo_incluye_privados_y_archivos_anteriores(tmp_path):
    git_bash = Path('C:/Program Files/Git/bin/bash.exe')
    bash = str(git_bash) if git_bash.exists() else shutil.which('bash')
    if not bash:
        pytest.skip('Requiere bash para probar el script del VPS')
    app = tmp_path / 'app'
    destino = tmp_path / 'copias'
    assert app.resolve().is_relative_to(tmp_path.resolve())
    assert destino.resolve().is_relative_to(tmp_path.resolve())
    (app / 'instance/private/pod').mkdir(parents=True)
    (app / 'web/static/uploads/pod').mkdir(parents=True)
    (app / '.env').write_text('SECRETO_SOLO_PRUEBA=1')
    (app / 'instance/private/pod/nueva.png').write_bytes(b'foto-privada')
    (app / 'web/static/uploads/pod/anterior.png').write_bytes(b'foto-anterior')
    fuente = (Path(__file__).resolve().parents[1] / 'scripts/vps/formopack-backup').read_text(encoding='utf-8')
    def ruta_bash(ruta):
        return '/' + ruta.drive[0].lower() + ruta.as_posix()[2:] if ruta.drive else ruta.as_posix()
    # Adaptar solo las raíces fijas al directorio exclusivo de esta prueba.
    fuente = fuente.replace('destino=/var/backups/formopack', f'destino="{ruta_bash(destino)}"')
    fuente = fuente.replace('app=/home/formopack/formopack-app', f'app="{ruta_bash(app)}"')
    fuente = fuente.replace('/run/lock/formopack-backup.lock', ruta_bash(tmp_path / 'bloqueo'))
    for ajeno in ('/var/backups/formopack', '/home/formopack/formopack-app', '/run/lock/'):
        assert ajeno not in fuente
    # Ninguna conexión SQL ni lectura del repositorio/credenciales del usuario.
    simulados = "\nmariadb-dump() { echo 'CREATE TABLE prueba (id INT)'; }\nflock() { return 0; }\ngit() { echo revision-de-prueba; }\n"
    fuente = fuente.replace('umask 077', 'umask 077' + simulados)
    script = tmp_path / 'respaldo-prueba.sh'
    script.write_text(fuente, encoding='utf-8', newline='\n')
    proceso = subprocess.run([bash, '--noprofile', '--norc', script.as_posix()], capture_output=True, text=True, timeout=30)
    assert proceso.returncode == 0, proceso.stderr
    copias = list(destino.glob('formopack-*.tar.gz'))
    assert len(copias) == 1
    with tarfile.open(copias[0]) as exterior:
        assert exterior.extractfile('./base.sql').read().startswith(b'CREATE TABLE prueba')
        contenido = exterior.extractfile('./archivos.tar.gz').read()
    with tarfile.open(fileobj=io.BytesIO(contenido)) as archivos:
        assert archivos.extractfile('instance/private/pod/nueva.png').read() == b'foto-privada'
        assert archivos.extractfile('web/static/uploads/pod/anterior.png').read() == b'foto-anterior'
        assert archivos.extractfile('.env').read() == b'SECRETO_SOLO_PRUEBA=1'
    assert (app / 'instance/private/pod/nueva.png').exists()
