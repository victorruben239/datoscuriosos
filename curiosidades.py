import feedparser
import sqlite3
import requests
import time
import re
import random
from groq import Groq
import datetime
import os
import json
import io


# --- 1. CONFIGURACIÓN ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MODELO = "llama-3.1-8b-instant"

# Directorio base (para que funcione en PythonAnywhere sin perderse)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Datos Facebook (IMPORTANTE: Usa el token de PÁGINA que sacamos)
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN")
ID_PAGINA_CURIOSIDADES = os.environ.get("ID_PAGINA_CURIOSIDADES")
FB_PAGE_ID = ID_PAGINA_CURIOSIDADES

# Inicializamos cliente Groq solo si hay Key, para evitar crash inmediato
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# --- 2. BASE DE DATOS ---
def inicializar_db():
    # Cambiamos 'noticias' por 'curiosidades'
    db_path = os.path.join(BASE_DIR, 'vIcmAr_curiosidades.db') 
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS posts (id_noticia TEXT PRIMARY KEY)''')
    conn.commit()
    return conn

# --- FUNCION LOG DE ERRORES ---
def log_error(mensaje):
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(BASE_DIR, 'errores.log'), 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {mensaje}\n")
    except: pass

# --- 3. REDACCIÓN CON IA ---
def transformar_con_ia(titulo, resumen):
    if not client:
        print("[ERROR] No se detectó GROQ_API_KEY. No se puede generar contenido.")
        return None, None

    try:
        # Filtramos cosas que no sean datos curiosos si es necesario
        if any(palabra in titulo.lower() for palabra in ["quiniela", "sorteo", "lotería", "clima", "pronostico", "pronóstico", "servicio", "política", "cookies", "administrar"]):
            return None, None

        prompt = f"""
        Actúa como un divulgador científico apasionado y carismático, creador de "Mente Curiosa AR". 
        Tu misión es que el lector se sienta más inteligente después de leerte.

        REGLAS DE ORO:
        1. EL GANCHO (Hook): Empieza con una pregunta contundente o un dato que desafíe la lógica. 
           - Ejemplo: "¿Sabías que hay más árboles en la Tierra que estrellas en nuestra galaxia?" o "¡Cuidado! Tu cerebro te está engañando ahora mismo..."

        2. EXPLICACIÓN SIMPLE: Explica el dato curioso como si se lo contaras a un amigo en un asado. Nada de tecnicismos aburridos. Usa analogías.

        3. ESTRUCTURA:
           - 🤯 [DATO IMPACTANTE EN MAYÚSCULAS] (Esta será la primera línea)
           - 🔬 LA EXPLICACIÓN: (2 o 3 párrafos cortos y dinámicos)
           - 💡 ¿SABÍAS QUÉ?: Un dato extra cortito relacionado.
           - 🇦🇷 TOQUE ARGENTINO: Usa un lenguaje cercano (voseo: "Mirá", "Fijate", "Contanos").
           - 🚀 LLAMADO A LA ACCIÓN: Pide explícitamente que sigan a la página "Mente Curiosa AR" para más datos diarios.

        4. INTERACCIÓN: Termina con una pregunta que invite a compartir o etiquetar a alguien.
           - Ejemplo: "¿A quién le enviarías este dato para dejarlo pensando?" o "¿Ya conocías este secreto de la naturaleza?"

        INFORMACIÓN BASE:
        Título: {titulo}
        Resumen: {resumen}
        
        REGLAS ESTRICTAS DE SALIDA:
        - Responde ÚNICAMENTE con el contenido del post.
        - NO incluyas saludos, introducciones ("Aquí tienes...", "Perfecto..."), ni notas finales.
        - Empieza DIRECTAMENTE con el título/gancho.
        
        ESTRUCTURA DE SALIDA:
        Línea 1: El Gancho (Título).
        Resto: El cuerpo del post con emojis y espacios.
        """
        
        completion = client.chat.completions.create(
            model=MODELO,
            messages=[
                {"role": "system", "content": "Eres un redactor experto. Tu respuesta debe contener SOLO el post final, sin saludos ni texto introductorio."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        
        respuesta = completion.choices[0].message.content
        lineas = respuesta.split('\n')
        
        # Limpieza agresiva del título para sacar "Título atractivo:" y asteriscos
        raw_title = lineas[0]
        raw_title = re.sub(r'<[^>]+>', '', raw_title)
        clean_title = re.sub(r'^(Título|Titulo|Headline|Asunto|Tema|Gancho)[:\s-]*', '', raw_title, flags=re.IGNORECASE)
        nuevo_titulo = clean_title.replace('**', '').replace('*', '').replace('"', '').replace("'", "").strip()
        
        cuerpo = "\n".join(lineas[1:])
        cuerpo = cuerpo.replace('**', '') # Eliminar asteriscos si la IA no obedeció
        return nuevo_titulo, cuerpo
    except: return None, None

def publicar_en_facebook(titulo, cuerpo_ia, imagen_url, hashtags="", es_video=False, link_original=""):
    # Limpieza de seguridad: Aunque la IA no debería mandar HTML, limpiamos por si acaso
    texto_limpio = cuerpo_ia.replace('<br>', '\n').replace('<br/>', '\n')
    texto_limpio = re.sub('<[^<]+?>', '', texto_limpio) # Elimina cualquier tag restante
    
    # Formateo final
    texto_fb = "\n\n".join([line.strip() for line in texto_limpio.splitlines() if line.strip()])
    
    # Mensaje final para Facebook
    mensaje_final = f"{titulo}\n\n{texto_fb}\n\n👇 ¡No te olvides de seguirnos para aprender algo nuevo cada día!\n{hashtags}"
    
    # Lógica para imagen: Usamos /photos si hay imagen (se ve más grande y bonita), sino /feed
    if es_video and link_original:
        # Si es video (YouTube), publicamos el LINK para que se vea el reproductor
        url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
        payload = {
            'message': mensaje_final,
            'link': link_original,
            'access_token': FB_PAGE_TOKEN
        }
        files = None
    elif imagen_url:
        # MEJORA MONETIZACIÓN: Descargar imagen y subirla nativamente (mayor alcance)
        try:
            print(f"[INFO] Descargando imagen para subida nativa: {imagen_url}")
            img_response = requests.get(imagen_url, timeout=10)
            if img_response.status_code == 200:
                url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
                payload = {
                    'message': mensaje_final,
                    'access_token': FB_PAGE_TOKEN
                }
                # Enviamos la imagen como archivo binario ('source')
                files = {
                    'source': ('imagen_curiosa.jpg', io.BytesIO(img_response.content), 'image/jpeg')
                }
            else:
                print("[WARN] No se pudo descargar la imagen, publicando solo texto.")
                url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
                payload = {'message': mensaje_final, 'access_token': FB_PAGE_TOKEN}
                files = None
        except Exception as e:
            print(f"[WARN] Error procesando imagen: {e}. Publicando solo texto.")
            url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
            payload = {'message': mensaje_final, 'access_token': FB_PAGE_TOKEN}
            files = None
    else:
        url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
        payload = {
            'message': mensaje_final,
            'access_token': FB_PAGE_TOKEN
        }
        files = None
    
    try:
        if files:
            r = requests.post(url, data=payload, files=files)
        else:
            r = requests.post(url, data=payload)
            
        resultado = r.json()
        if r.status_code == 200:
            post_id = resultado.get('id', 'Desconocido')
            print(f"[OK] Publicado en Facebook con exito! ID: {post_id}")
            return True
        else:
            # Si vuelve a fallar, el error nos dirá exactamente qué permiso falta
            error_data = resultado.get('error', {})
            msg = error_data.get('message', 'Error desconocido')
            code = error_data.get('code')
            
            print(f"[ALERTA] Detalle del error: {msg}")
            log_error(f"Facebook API Error: {msg}")
            
            if code == 200 or "(#200)" in msg:
                print("\n[!!!] ERROR CRÍTICO DE PERMISOS: Tu Token no sirve.")
                print("      SOLUCIÓN: Genera un nuevo Token y asegúrate de marcar: 'pages_manage_posts' y 'pages_read_engagement'.\n")
            return False
    except Exception as e:
        print(f"[ERROR] Conexion FB: {e}")
        log_error(f"Excepcion FB: {e}")
        return False

# --- FUNCION AUXILIAR: HASHTAGS ---
def obtener_hashtags(url_fuente):
    return "#Curiosidades #DatosCuriosos #SabiasQue #MenteCuriosaAR #Ciencia #Viral #Mundo #Aprender"

# --- 5. FUNCIÓN PRINCIPAL DEL BOT ---
def ejecutar_bot(url_rss):
    conn = inicializar_db()
    cursor = conn.cursor()
    
    print(f"[INFO] Analizando fuente: {url_rss}")
    try:
        feed = feedparser.parse(url_rss)
    except Exception as e:
        print(f"[ERROR] Leyendo RSS: {e}")
        conn.close()
        return False

    # Procesamos las primeras noticias hasta encontrar una nueva
    for entry in feed.entries[:3]:
        try:
            guid = entry.link
            
            # Verificar si ya existe en la base de datos
            cursor.execute("SELECT id_noticia FROM posts WHERE id_noticia = ?", (guid,))
            if cursor.fetchone():
                continue
                
            # Lista de palabras prohibidas (basura de RSS)
            prohibidas = ["utiq", "aviso legal", "cookies", "privacidad", "términos y condiciones", "suscríbete"]
            if any(palabra in entry.title.lower() for palabra in prohibidas):
                print(f"[SKIP] Noticia descartada por filtro de calidad: {entry.title}")
                continue

            print(f"[INFO] Procesando: {entry.title}")
            
            # 1. Detectar si es video (ej: YouTube)
            es_video = "youtube.com" in guid or "youtu.be" in guid
            
            # 2. Intentar obtener imagen (si no es video)
            imagen = ""
            if not es_video:
                if hasattr(entry, 'media_content') and entry.media_content:
                    imagen = entry.media_content[0].get('url', '')
                elif hasattr(entry, 'enclosures') and entry.enclosures:
                    imagen = entry.enclosures[0].get('href', '')
                
                # Si no hay imagen en el RSS, intentamos buscarla en la web original (og:image)
                if not imagen:
                    try:
                        # Usamos un regex simple para no obligar a instalar BeautifulSoup
                        # Mejorado para aceptar comillas simples o dobles
                        r_html = requests.get(guid, timeout=5).text
                        match = re.search(r'<meta property="og:image" content=["\']([^"\']+)["\']', r_html)
                        if match:
                            imagen = match.group(1)
                        else:
                            # Intento secundario con twitter:image para asegurar mas imagenes
                            match_tw = re.search(r'<meta name="twitter:image" content=["\']([^"\']+)["\']', r_html)
                            if match_tw:
                                imagen = match_tw.group(1)
                    except:
                        pass
                
            # Generar contenido con IA
            nuevo_titulo, cuerpo = transformar_con_ia(entry.title, getattr(entry, 'summary', ''))
            
            # Obtener hashtags según la fuente
            tags = obtener_hashtags(url_rss)
            
            if nuevo_titulo and cuerpo:
                # Publicamos SOLO en Facebook
                if publicar_en_facebook(nuevo_titulo, cuerpo, imagen, tags, es_video, guid):
                    # Guardamos en DB SOLO si se publicó correctamente
                    cursor.execute("INSERT INTO posts VALUES (?)", (guid,))
                    conn.commit()
                    conn.close()
                    return True # Retornamos True para contar la publicación
                else:
                    print("[WARN] No se guardó en DB para reintentar luego.")

        except Exception as e:
            print(f"[ERROR] Falló al procesar entrada: {e}")
            log_error(f"Error procesando {entry.link}: {e}")
            continue
            
    conn.close()
    return False

# --- 6. EJECUCIÓN MULTI-FUENTE ---
def iniciar_escaneo():
    lista_fuentes = [
        # --- CURIOSIDADES Y CIENCIA (Fuentes puras) ---
        "https://www.nationalgeographic.com.es/feeds/rss/", 
        "https://www.muyinteresante.com.mx/feed", 
        "https://www.bbc.com/mundo/temas/ciencia/index.xml",
        "https://www.xatakaciencia.com/index.xml", # Agregado: Excelente fuente de curiosidades
        # Agregá estas URLs a tu lista_fuentes:
        "https://www.muyinteresante.es/rss",
        "https://www.ojocientifico.com/feed",
        "https://www.quo.es/rss",
        "https://hipertextual.com/feed",
        "https://www.agenciasinc.es/var/ezflow_site/storage/rss/rss_portada.xml", # Agencia SINC (Excelente fuente)
        "https://www.robotitus.com/feed", # Robotitus
        "https://es.wired.com/feed/category/ciencia", # Wired Ciencia
        
        # --- VIDEOS (YouTube RSS) ---
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCyQcO-59oY_FkQ5g54lWAPg", # En Pocas Palabras
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCw0jE-Vz7-t1c3z_q5c6e7w", # GENIAL (Videos virales de curiosidades)
    ]
    
    # Mezclamos las fuentes para que no siempre empiece por las mismas
    random.shuffle(lista_fuentes)
    
    publicaciones_ciclo = 0
    LIMITE_CICLO = 1 # Máximo de noticias a publicar por ciclo (reducido para no hacer spam)
    
    print("[INFO] --- Iniciando ciclo de Mente Curiosa AR ---")
    
    for url in lista_fuentes:
        if publicaciones_ciclo >= LIMITE_CICLO:
            print("[INFO] Limite de publicaciones por ciclo alcanzado.")
            break
            
        if ejecutar_bot(url):
            publicaciones_ciclo += 1
            print(f"[INFO] Publicaciones en este ciclo: {publicaciones_ciclo}/{LIMITE_CICLO}")
            time.sleep(30) # Pausa de seguridad entre publicaciones
    
    print(f"\n[INFO] Ciclo completado. Se publicaron {publicaciones_ciclo} datos.")
    print(f"Hora de finalización: {time.ctime()}")
    


# --- 6. BUCLE DE REPETICIÓN CADA 30 MINUTOS ---
if __name__ == "__main__":
    print("[INFO] Iniciando ejecución en GitHub Actions...")
    try:
        iniciar_escaneo()
        print("[OK] Ejecución finalizada correctamente.")
    except Exception as e:
        print(f"[ERROR] Ocurrió un error: {e}")
