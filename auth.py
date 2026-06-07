# auth.py - Agregar a tu proyecto FastAPI en Railway
# pip install supabase python-jose
 
import os
from fastapi import HTTPException, Header
from typing import Optional
from supabase import create_client, Client
 
SUPABASE_URL = "https://snhkkptrpqshjjehtsgz.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNuaGtrcHRycHFzaGpqZWh0c2d6Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDc3NjcyMiwiZXhwIjoyMDk2MzUyNzIyfQ.OqXi4xmEQidwtmcbyAWQeLq3acdkCHdNVi_9hf32LWU"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
 
 
def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """
    Extrae y verifica el JWT de Supabase del header Authorization.
    Retorna el usuario si es válido, None si no hay token (guest).
    Lanza 401 si el token es inválido.
    """
    if not authorization:
        return None  # Usuario sin cuenta (guest)
 
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Formato de token inválido")
 
    token = authorization.replace("Bearer ", "")
 
    try:
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")
        return {"id": user.user.id, "email": user.user.email}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Token inválido: {}".format(str(e)))
 
 
def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """
    Igual que get_current_user pero lanza 401 si no hay token.
    Usar en endpoints que requieren cuenta obligatoria.
    """
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Esta función requiere iniciar sesión en CatFile 🐾"
        )
    return user
 
 
def check_usage(user_id: str, action: str) -> bool:
    """
    Verifica y registra el uso de una acción para un usuario.
    Llama a la función SQL check_and_increment_usage.
    Retorna True si puede continuar, False si alcanzó el límite.
    """
    try:
        result = supabase.rpc(
            "check_and_increment_usage",
            {"p_user_id": user_id, "p_action": action}
        ).execute()
        return result.data
    except Exception as e:
        print("[Auth] Error verificando límite: {}".format(str(e)))
        return True  # En caso de error, permitir para no bloquear al usuario
 
 
def get_user_plan(user_id: str) -> str:
    """Obtiene el plan del usuario (free | premium)"""
    try:
        result = supabase.table("profiles").select("plan").eq("id", user_id).single().execute()
        return result.data.get("plan", "free")
    except:
        return "free"
 
 
def save_pdf_to_db(user_id: Optional[str], pdf_id: str, filename: str, text: str, size_bytes: int):
    """
    Guarda el PDF en Supabase para persistencia.
    Si user_id es None (guest), solo guarda en memoria local (pdf_storage).
    """
    if not user_id:
        return  # Guests usan solo el dict en memoria
 
    try:
        supabase.table("pdf_files").upsert({
            "user_id": user_id,
            "pdf_id": pdf_id,
            "filename": filename,
            "text": text[:500000],  # Limitar a 500KB de texto
            "size_bytes": size_bytes,
        }).execute()
        print("[Auth] PDF {} guardado en DB para usuario {}".format(pdf_id, user_id))
    except Exception as e:
        print("[Auth] Error guardando PDF en DB: {}".format(str(e)))
 
 
def load_pdf_from_db(user_id: str, pdf_id: str) -> Optional[str]:
    """
    Recupera el texto de un PDF desde Supabase.
    Útil cuando el servidor se reinició y perdió el pdf_storage en memoria.
    """
    try:
        result = supabase.table("pdf_files") \
            .select("text, filename") \
            .eq("pdf_id", pdf_id) \
            .eq("user_id", user_id) \
            .single() \
            .execute()
        return result.data
    except:
        return None