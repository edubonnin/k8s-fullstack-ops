import os
import boto3
from botocore.exceptions import ClientError

# Configuración
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY')
MINIO_BUCKET = os.getenv('MINIO_BUCKET')

def get_minio_client():
    if not all([MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET]):
         print("❌ Error: Faltan variables de entorno para MinIO.")
         return None
    try:
        endpoint = MINIO_ENDPOINT
        if not endpoint.startswith('http'):
            endpoint = f"http://{endpoint}"

        s3 = boto3.client('s3',
                          endpoint_url=endpoint,
                          aws_access_key_id=MINIO_ACCESS_KEY,
                          aws_secret_access_key=MINIO_SECRET_KEY,
                          config=boto3.session.Config(signature_version='s3v4'),
                          region_name='us-east-1')
        return s3
    except Exception as e:
        print(f"❌ Error conectando a MinIO: {e}")
        return None

def upload_assets():
    print(f"🚀 Iniciando carga de assets a MinIO ({MINIO_ENDPOINT})...")
    s3 = get_minio_client()
    if not s3:
        return

    # Buscar en la carpeta static
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    
    if not os.path.exists(static_dir):
        print(f"⚠️ No se encontró la carpeta {static_dir}")
        return

    files_uploaded = 0
    for filename in os.listdir(static_dir):
        # Subir únicamente imágenes
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.ico')):
            file_path = os.path.join(static_dir, filename)
            try:
                # El Key en el bucket será el nombre del archivo
                print(f"📤 Subiendo {filename} a bucket '{MINIO_BUCKET}'...")
                s3.upload_file(file_path, MINIO_BUCKET, filename)
                files_uploaded += 1
            except ClientError as e:
                print(f"❌ Error subiendo {filename}: {e}")

    if files_uploaded > 0:
        print(f"✅ {files_uploaded} archivos subidos correctamente.")
    else:
        print("ℹ️ No se encontraron archivos nuevos para subir.")

if __name__ == "__main__":
    upload_assets()
