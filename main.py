from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from auth import get_current_user, require_auth, check_usage, get_user_plan, save_pdf_to_db, load_pdf_from_db
from fastapi.responses import StreamingResponse
import pymupdf
import io
import uuid
import os
import base64
import google.generativeai as genai

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

app = FastAPI(title="CatFile API", description="API para edición profesional de PDFs 🐾")

@app.get("/")
def root():
    return {"message": "CatFile API funcionando 🐾", "version": "1.0.0"}

@app.post("/pdf/get-text")
async def get_pdf_text(file: UploadFile = File(...)):
    """Extrae todo el texto de un PDF con posiciones"""
    try:
        content = await file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            text_blocks = []
            for block in blocks:
                if block["type"] == 0:  # texto
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text_blocks.append({
                                "text": span["text"],
                                "x": span["bbox"][0],
                                "y": span["bbox"][1],
                                "size": span["size"],
                                "font": span["font"],
                                "page": page_num
                            })
            pages.append(text_blocks)
        
        doc.close()
        return {"pages": pages, "total_pages": len(pages)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/edit-text")
async def edit_pdf_text(
    file: UploadFile = File(...),
    old_text: str = Form(...),
    new_text: str = Form(...),
    page_num: int = Form(0)
):
    """Reemplaza texto en un PDF"""
    try:
        print("[CatFileAPI] EDIT-TEXT: Iniciando edición de texto - página: {}".format(page_num))
        content = await file.read()
        
        if not old_text.strip():
            raise HTTPException(status_code=400, detail="old_text no puede estar vacío")
        
        # Validar con la información del documento
        doc_info = PDFAssistantService.get_doc_info(content)
        if page_num >= doc_info["total_pages"]:
            raise HTTPException(status_code=400, detail="Página {} fuera de rango".format(page_num))
        
        # Usar el servicio centralizado
        pdf_bytes = await PDFAssistantService.edit_text_service(content, old_text, new_text, page_num)
        
        output = io.BytesIO(pdf_bytes)
        print("[CatFileAPI] EDIT-TEXT: Completado exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] EDIT-TEXT: Error - {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/edit-image")
async def edit_image(
    file: UploadFile = File(...),
    image_index: int = Form(...),
    x: float = Form(None),
    y: float = Form(None),
    width: float = Form(None),
    height: float = Form(None),
    rotation: int = Form(0)
):
    """Edita imágenes existentes en el PDF: mover, redimensionar y rotar"""
    try:
        print("[CatFileAPI] Iniciando edición de imagen - índice: {}, rotación: {}".format(image_index, rotation))
        content = await file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        image_found = False
        for page_num in range(len(doc)):
            page = doc[page_num]
            images = page.get_images(full=True)
            
            if image_index < len(images):
                print("[CatFileAPI] Imagen encontrada en página {} en índice {}".format(page_num, image_index))
                xref = images[image_index][0]
                
                # Obtener información actual de la imagen
                image_rects = page.get_image_rects(xref)
                if image_rects:
                    rect = image_rects[0]
                    print("[CatFileAPI] Posición actual: {}".format(rect))
                    
                    # Calcular nuevas dimensiones
                    new_x = x if x is not None else rect.x0
                    new_y = y if y is not None else rect.y0
                    new_width = width if width is not None else (rect.x1 - rect.x0)
                    new_height = height if height is not None else (rect.y1 - rect.y0)
                    
                    new_rect = pymupdf.Rect(new_x, new_y, new_x + new_width, new_y + new_height)
                    
                    # Detectar el color de fondo de la página
                    try:
                        pixmap = page.get_pixmap(alpha=False)
                        pixel_data = pixmap.pixel(0, 0)
                        
                        if isinstance(pixel_data, int):
                            gray_val = pixel_data / 255.0
                            bg_color = (gray_val, gray_val, gray_val)
                        else:
                            bg_color = tuple(c / 255.0 for c in pixel_data[:3])
                        
                        print("[CatFileAPI] Color de fondo detectado: {}".format(bg_color))
                    except:
                        bg_color = (1, 1, 1)
                        print("[CatFileAPI] No se pudo detectar color de fondo, usando blanco por defecto")
                    
                    # Cubrir el área original con rectángulo del color de fondo
                    print("[CatFileAPI] Cubriendo área original: {}".format(rect))
                    page.draw_rect(rect, color=bg_color, fill=bg_color)
                    
                    # Reinsertar la imagen en la nueva posición
                    print("[CatFileAPI] Reinsertando imagen en nueva posición: {}".format(new_rect))
                    if rotation != 0:
                        print("[CatFileAPI] Aplicando rotación de {} grados".format(rotation))
                        page.insert_image(new_rect, xref=xref, rotate=rotation)
                    else:
                        page.insert_image(new_rect, xref=xref)
                    
                    print("[CatFileAPI] Nueva posición: {}".format(new_rect))
                    image_found = True
                    break
        
        if not image_found:
            raise HTTPException(status_code=404, detail="Imagen no encontrada en el índice especificado")
        
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        
        print("[CatFileAPI] PDF modificado exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] Error en edit-image: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/add-image")
async def add_image(
    file: UploadFile = File(...),
    image: UploadFile = File(...),
    page_num: int = Form(0),
    x: float = Form(0),
    y: float = Form(0),
    width: float = Form(100),
    height: float = Form(100)
):
    """Añade una nueva imagen al PDF"""
    try:
        print("[CatFileAPI] Iniciando adición de imagen en página {} - posición ({}, {})".format(page_num, x, y))
        content = await file.read()
        image_content = await image.read()
        
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        if page_num >= len(doc):
            raise HTTPException(status_code=400, detail="Número de página inválido")
        
        page = doc[page_num]
        rect = pymupdf.Rect(x, y, x + width, y + height)
        
        # Guardar imagen temporalmente
        image_stream = io.BytesIO(image_content)
        print("[CatFileAPI] Insertando imagen en rectángulo: {}".format(rect))
        page.insert_image(rect, stream=image_stream, pixmap=None)
        
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        
        print("[CatFileAPI] Imagen añadida exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] Error en add-image: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/delete-image")
async def delete_image(
    file: UploadFile = File(...),
    page_num: int = Form(...),
    image_index: int = Form(...)
):
    """Elimina una imagen del PDF"""
    try:
        print("[CatFileAPI] DELETE-IMAGE: Iniciando eliminación - página: {}, índice: {}".format(page_num, image_index))
        content = await file.read()
        
        # Validar con la información del documento
        doc_info = PDFAssistantService.get_doc_info(content)
        if page_num >= doc_info["total_pages"]:
            raise HTTPException(status_code=400, detail="Página {} fuera de rango".format(page_num))
        
        # Usar el servicio centralizado
        pdf_bytes = await PDFAssistantService.delete_image_service(content, page_num, image_index)
        
        output = io.BytesIO(pdf_bytes)
        print("[CatFileAPI] DELETE-IMAGE: Completado exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] DELETE-IMAGE: Error - {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/add-signature")
async def add_signature(
    file: UploadFile = File(...),
    signature_image: UploadFile = File(...),
    page_num: int = Form(0),
    x: float = Form(0),
    y: float = Form(0),
    width: float = Form(100),
    height: float = Form(50)
):
    """Añade una firma (imagen PNG transparente) al PDF"""
    try:
        print("[CatFileAPI] Iniciando adición de firma en página {} - posición ({}, {})".format(page_num, x, y))
        content = await file.read()
        signature_content = await signature_image.read()
        
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        if page_num >= len(doc):
            raise HTTPException(status_code=400, detail="Número de página inválido")
        
        page = doc[page_num]
        rect = pymupdf.Rect(x, y, x + width, y + height)
        
        signature_stream = io.BytesIO(signature_content)
        print("[CatFileAPI] Insertando firma en rectángulo: {}".format(rect))
        page.insert_image(rect, stream=signature_stream, pixmap=None)
        
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        
        print("[CatFileAPI] Firma añadida exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=signed.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] Error en add-signature: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/delete-page")
async def delete_page(
    file: UploadFile = File(...),
    pages: str = Form(...)
):
    """Elimina páginas del PDF (pasar como string JSON: '[0,2,5]')"""
    try:
        print("[CatFileAPI] DELETE-PAGE: Iniciando eliminación de páginas: {}".format(pages))
        content = await file.read()
        
        import json
        try:
            pages_to_delete = json.loads(pages)
        except:
            raise HTTPException(status_code=400, detail="Formato de páginas inválido. Debe ser JSON: '[0,2,5]'")
        
        # Validar con la información del documento
        doc_info = PDFAssistantService.get_doc_info(content)
        for page_num in pages_to_delete:
            if page_num < 0 or page_num >= doc_info["total_pages"]:
                raise HTTPException(status_code=400, detail="Página {} fuera de rango (0-{})".format(
                    page_num, doc_info["total_pages"]-1))
        
        # Usar el servicio centralizado
        pdf_bytes = await PDFAssistantService.delete_page_service(content, pages_to_delete)
        
        output = io.BytesIO(pdf_bytes)
        print("[CatFileAPI] DELETE-PAGE: Completado exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] DELETE-PAGE: Error - {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/add-page")
async def add_page(
    file: UploadFile = File(...),
    position: int = Form(-1)
):
    """Añade una página en blanco al PDF (position=-1 al final)"""
    try:
        print("[CatFileAPI] ADD-PAGE: Iniciando adición de página - posición: {}".format(position))
        content = await file.read()
        
        # Usar el servicio centralizado
        pdf_bytes = await PDFAssistantService.add_page_service(content, position)
        
        output = io.BytesIO(pdf_bytes)
        print("[CatFileAPI] ADD-PAGE: Completado exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] ADD-PAGE: Error - {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/reorder-pages")
async def reorder_pages(
    file: UploadFile = File(...),
    order: str = Form(...)
):
    """Reordena las páginas del PDF (pasar como string JSON: '[2,0,1]')"""
    try:
        print("[CatFileAPI] REORDER-PAGES: Iniciando reordenamiento - {}".format(order))
        content = await file.read()
        
        import json
        try:
            new_order = json.loads(order)
        except:
            raise HTTPException(status_code=400, detail="Formato de orden inválido. Debe ser JSON: '[2,0,1]'")
        
        # Validar con la información del documento
        doc_info = PDFAssistantService.get_doc_info(content)
        
        if len(new_order) != doc_info["total_pages"]:
            raise HTTPException(status_code=400, detail="El número de páginas no coincide")
        
        if set(new_order) != set(range(doc_info["total_pages"])):
            raise HTTPException(status_code=400, detail="Los índices de página deben ser únicos y estar entre 0 y {}".format(
                doc_info["total_pages"]-1))
        
        # Usar el servicio centralizado
        pdf_bytes = await PDFAssistantService.reorder_pages_service(content, new_order)
        
        output = io.BytesIO(pdf_bytes)
        print("[CatFileAPI] REORDER-PAGES: Completado exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] REORDER-PAGES: Error - {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/get-images")
async def get_images(
    file: UploadFile = File(...),
    page_num: int = Form(0)
):
    """Obtiene lista de imágenes en el PDF con sus posiciones y dimensiones"""
    try:
        print("[CatFileAPI] Obteniendo imágenes de página {}".format(page_num))
        content = await file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        if page_num >= len(doc):
            raise HTTPException(status_code=400, detail="Número de página inválido")
        
        page = doc[page_num]
        images = page.get_images()
        
        images_list = []
        for idx, img_info in enumerate(images):
            xref = img_info[0]
            image_rects = page.get_image_rects(xref)
            
            if image_rects:
                rect = image_rects[0]
                images_list.append({
                    "index": idx,
                    "xref": xref,
                    "x": rect.x0,
                    "y": rect.y0,
                    "width": rect.x1 - rect.x0,
                    "height": rect.y1 - rect.y0,
                    "position": {"x0": rect.x0, "y0": rect.y0, "x1": rect.x1, "y1": rect.y1}
                })
                print("[CatFileAPI] Imagen {} encontrada en posición ({}, {})".format(idx, rect.x0, rect.y0))
        
        doc.close()
        
        print("[CatFileAPI] Total de imágenes en página {}: {}".format(page_num, len(images_list)))
        return {
            "page": page_num,
            "total_images": len(images_list),
            "images": images_list
        }
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] Error en get-images: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/add-text")
async def add_text_to_pdf(
    file: UploadFile = File(...),
    text: str = Form(...),
    page_num: int = Form(0),
    x: float = Form(50),
    y: float = Form(50),
    fontsize: float = Form(12),
    color: str = Form("#000000")  # ✅ agregar este parámetro
):
    try:
        print("[CatFileAPI] ADD-TEXT: página={}, x={}, y={}, color={}".format(page_num, x, y, color))
        content = await file.read()
        
        pdf_bytes = await PDFAssistantService.add_text_service(
            content, text, page_num, x, y, fontsize, color)  # ✅ pasar color
        
        output = io.BytesIO(pdf_bytes)
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except Exception as e:
        print("[CatFileAPI] ADD-TEXT Error: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ocr/extract")
async def ocr_extract(request: Request):
    """Extrae texto de una imagen usando Gemini"""
    try:
        body = await request.json()
        image_base64 = body.get("image_base64")
        mime_type = body.get("mime_type", "image/jpeg")
        
        if not image_base64:
            raise HTTPException(status_code=400, detail="image_base64 es requerido")
        
        print("[CatFileAPI] OCR: Extrayendo texto de imagen")
        
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        image_data = base64.b64decode(image_base64)
        
        import PIL.Image
        import io as _io
        img = PIL.Image.open(_io.BytesIO(image_data))
        
        response = model.generate_content([
            "Por favor, extrae TODA la información de texto visible en esta imagen. "
            "Incluye todos los textos, números, palabras clave, títulos y contenido. "
            "Devuelve solo el texto extraído sin explicaciones adicionales.",
            img
        ])
        
        print("[CatFileAPI] OCR: Texto extraído correctamente")
        return {"text": response.text}
        
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] OCR Error: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summarize")
async def summarize_text(request: Request):
    """Resume un texto usando Gemini"""
    try:
        body = await request.json()
        text = body.get("text")
        
        if not text:
            raise HTTPException(status_code=400, detail="text es requerido")
        
        print("[CatFileAPI] Summarize: Resumiendo texto")
        
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        response = model.generate_content(
            "Resume el siguiente texto en un párrafo breve, manteniendo "
            "las ideas principales. Devuelve solo el resumen:\n\n" + text[:50000]
        )
        
        print("[CatFileAPI] Summarize: Resumen generado")
        return {"summary": response.text}
        
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] Summarize Error: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# MÓDULO ASISTENTE: Parser de Instrucciones Naturales
# =====================================================

import re
import json
from typing import List, Dict, Any, Tuple

class PDFAssistantParser:
    """Parser de instrucciones en lenguaje natural para operaciones PDF"""
    
    def __init__(self, language="es"):
        self.language = language
        self.doc = None  # Se asigna cuando se procesa
        
        # Patrones en español
        self.patterns_es = {
            "delete_page": r"(?:elimina|borra|quita|remueve)\s+(?:la\s+)?p[áa]gina[s]?\s+(\d+(?:\s*,\s*\d+)*|\[[\d\s,]+\])",
            "add_page": r"(?:a[ñn]ade|agrega|inserta)\s+(?:una\s+)?p[áa]gina\s+(?:en\s+blanco\s+)?(?:al\s+)?(?:final|final|final de documento)",
            "add_page_position": r"(?:a[ñn]ade|agrega|inserta)\s+(?:una\s+)?p[áa]gina\s+(?:en\s+blanco\s+)?(?:en\s+)?(?:posici[óo]n|posición)\s+(\d+)",
            "reorder_pages": r"(?:reordena|ordena|reorganiza)\s+las\s+p[áa]ginas\s+(?:como|en|en el orden)\s+(.+?)(?:\.|$)",
            "edit_text": r"(?:cambia|reemplaza|sustituye|remplaza)\s+['\"]?([^'\"]+)['\"]?\s+(?:por|con)\s+['\"]?([^'\"]+)['\"]?",
            "delete_image": r"(?:elimina|borra|quita)\s+(?:la\s+)?(?:imagen|foto|gr[áa]fico)\s+(?:principal|n[úu]mero\s+)?(\d+)?",
            "add_image": r"(?:a[ñn]ade|agrega|inserta)\s+(?:una\s+)?(?:imagen|foto|gr[áa]fico)",
            "add_signature": r"(?:a[ñn]ade|agrega|inserta)\s+(?:una\s+)?firma",
            "move_image": r"(?:mueve|desplaza|posiciona)\s+(?:la\s+)?(?:imagen|foto|gr[áa]fico)\s+(?:a\s+)?(\(?\d+\s*,\s*\d+\)?)",
            "get_text": r"(?:obtén|obtiene|extrae|saca)\s+(?:el\s+)?(?:texto|contenido|informaci[óo]n)",
            "get_images": r"(?:obtén|obtiene|extrae|lista|muestra)\s+(?:todas?\s+)?(?:las\s+)?(?:imágenes|fotos|gr[áa]ficos)",
        }
        
        # Patrones en inglés (para futuro)
        self.patterns_en = {
            "delete_page": r"(?:delete|remove|drop|erase)\s+(?:the\s+)?pages?\s+(\d+(?:\s*,\s*\d+)*|\[[\d\s,]+\])",
            "add_page": r"(?:add|insert|create)\s+(?:a\s+)?(?:blank\s+)?page\s+(?:at\s+)?(?:the\s+end|end)",
            "edit_text": r"(?:change|replace|substitute|swap)\s+['\"]?([^'\"]+)['\"]?\s+(?:with|for)\s+['\"]?([^'\"]+)['\"]?",
            "delete_image": r"(?:delete|remove|erase)\s+(?:the\s+)?(?:image|picture|graphic)\s+(?:number\s+)?(\d+)?",
            "add_signature": r"(?:add|insert|place)\s+(?:a\s+)?(?:signature|sign)",
        }
        
        self.patterns = self.patterns_es if language == "es" else self.patterns_en
    
    def extract_numbers(self, text: str) -> List[int]:
        """Extrae números de texto, convierte de 1-indexed a 0-indexed"""
        numbers = re.findall(r'\d+', text)
        return [int(n) - 1 for n in numbers]  # Conversión a 0-indexed
    
    def extract_page_range(self, text: str, doc_pages: int) -> List[int]:
        """Extrae rango de páginas y valida"""
        numbers = self.extract_numbers(text)
        
        if not numbers:
            raise ValueError("No se encontraron números de página")
        
        # Validar rango
        invalid = [n+1 for n in numbers if n >= doc_pages or n < 0]
        if invalid:
            raise ValueError("Página(s) {} fuera de rango (documento tiene {} páginas)".format(
                invalid, doc_pages))
        
        return numbers
    
    def parse_coordinate(self, text: str) -> Tuple[float, float]:
        """Extrae coordenadas (x, y) del texto"""
        match = re.search(r'\(?\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\s*\)?', text)
        if match:
            return float(match.group(1)), float(match.group(2))
        raise ValueError("No se encontraron coordenadas válidas")
    
    def detect_ambiguity(self, instruction: str, doc) -> str:
        """Detecta ambigüedades en la instrucción"""
        lower_inst = instruction.lower()
        doc_pages = len(doc)
        doc_images = sum(len(doc[p].get_images()) for p in range(doc_pages))
        
        # Verificar referencias sin parámetro
        if re.search(r'elimina\s+(?:la|esa|esta)\s+(?:imagen|página)', lower_inst) and \
           not re.search(r'\d', instruction.split("imagen")[0].split("página")[-1] if "imagen" in lower_inst or "página" in lower_inst else ""):
            
            if "imagen" in lower_inst and doc_images > 1:
                return "❌ No puedo identificar qué imagen deseas eliminar. ¿Cuál es el número de imagen?"
            elif "página" in lower_inst and doc_pages > 1:
                return "❌ ¿Qué página deseas eliminar? (especifica el número)"
        
        if re.search(r'mueve\s+(?:la|esa)\s+p[áa]gina', lower_inst) and \
           not re.search(r'posici[óo]n\s+\d', instruction):
            return "❌ ¿Qué página deseas mover y a qué posición?"
        
        if re.search(r'reordena', lower_inst) and \
           not any(str(i) in instruction for i in range(1, min(4, doc_pages+1))):
            return "❌ Especifica el nuevo orden de páginas (ej: 'páginas 2, 1, 3')"
        
        return None
    
    def parse(self, instruction: str, doc) -> List[Dict[str, Any]]:
        """Parsea instrucción y devuelve lista de operaciones"""
        self.doc = doc
        operations = []
        
        # Validar ambigüedad
        ambiguity_msg = self.detect_ambiguity(instruction, doc)
        if ambiguity_msg:
            raise ValueError(ambiguity_msg)
        
        lower_inst = instruction.lower()
        
        print("[CatFileAPI] Parseando instrucción: {}".format(instruction))
        
        # Detectar operaciones en orden de especificidad
        
        # 1. ELIMINAR PÁGINAS
        match = re.search(self.patterns["delete_page"], lower_inst)
        if match:
            page_str = match.group(1)
            pages = self.extract_page_range(page_str, len(doc))
            operations.append({
                "operation": "delete_page",
                "params": {"pages": pages},
                "description": "Eliminar páginas: {}".format([p+1 for p in pages])
            })
            print("[CatFileAPI] Detectado: delete_page - {}".format(pages))
        
        # 2. AÑADIR PÁGINA AL FINAL
        if re.search(self.patterns["add_page"], lower_inst) and \
           not re.search(self.patterns["add_page_position"], lower_inst):
            operations.append({
                "operation": "add_page",
                "params": {"position": -1},
                "description": "Añadir página al final"
            })
            print("[CatFileAPI] Detectado: add_page (final)")
        
        # 3. AÑADIR PÁGINA EN POSICIÓN
        match = re.search(self.patterns["add_page_position"], lower_inst)
        if match:
            pos = int(match.group(1)) - 1  # Convertir a 0-indexed
            operations.append({
                "operation": "add_page",
                "params": {"position": pos},
                "description": "Añadir página en posición {}".format(pos+1)
            })
            print("[CatFileAPI] Detectado: add_page - posición {}".format(pos))
        
        # 4. REORDENAR PÁGINAS
        match = re.search(self.patterns["reorder_pages"], lower_inst)
        if match:
            order_str = match.group(1)
            order = self.extract_numbers(order_str)
            
            if len(order) != len(doc):
                raise ValueError("El número de páginas no coincide. Documento tiene {} páginas, especificaste {}".format(
                    len(doc), len(order)))
            
            operations.append({
                "operation": "reorder_pages",
                "params": {"order": order},
                "description": "Reordenar páginas: {}".format([o+1 for o in order])
            })
            print("[CatFileAPI] Detectado: reorder_pages - {}".format(order))
        
        # 5. EDITAR TEXTO
        match = re.search(self.patterns["edit_text"], lower_inst)
        if match:
            old_text = match.group(1).strip()
            new_text = match.group(2).strip()
            
            operations.append({
                "operation": "edit_text",
                "params": {"old_text": old_text, "new_text": new_text, "page_num": 0},
                "description": "Reemplazar '{}' por '{}'".format(old_text, new_text)
            })
            print("[CatFileAPI] Detectado: edit_text - {} → {}".format(old_text, new_text))
        
        # 6. ELIMINAR IMAGEN
        match = re.search(self.patterns["delete_image"], lower_inst)
        if match:
            image_idx = match.group(1)
            if not image_idx:
                raise ValueError("❌ ¿Qué imagen deseas eliminar? (especifica el número)")
            
            image_idx = int(image_idx) - 1  # Convertir a 0-indexed
            
            # Encontrar página con la imagen
            page_found = None
            for page_num in range(len(doc)):
                images = doc[page_num].get_images()
                if image_idx < len(images):
                    page_found = page_num
                    break
            
            if page_found is None:
                raise ValueError("Imagen {} no encontrada en el documento".format(image_idx+1))
            
            operations.append({
                "operation": "delete_image",
                "params": {"page_num": page_found, "image_index": image_idx},
                "description": "Eliminar imagen {} de página {}".format(image_idx+1, page_found+1)
            })
            print("[CatFileAPI] Detectado: delete_image - {}".format(image_idx))
        
        # 7. AÑADIR FIRMA
        if re.search(self.patterns["add_signature"], lower_inst):
            operations.append({
                "operation": "add_signature",
                "params": {"page_num": -1, "requires_file": True},
                "description": "Añadir firma (se requiere archivo de imagen)"
            })
            print("[CatFileAPI] Detectado: add_signature")
        
        # 8. OBTENER TEXTO
        if re.search(self.patterns["get_text"], lower_inst):
            operations.append({
                "operation": "get_text",
                "params": {},
                "description": "Extraer todo el texto"
            })
            print("[CatFileAPI] Detectado: get_text")
        
        # 9. OBTENER IMÁGENES
        if re.search(self.patterns["get_images"], lower_inst):
            operations.append({
                "operation": "get_images",
                "params": {"page_num": 0},
                "description": "Listar imágenes"
            })
            print("[CatFileAPI] Detectado: get_images")
        
        if not operations:
            raise ValueError("No pude identificar ninguna operación en: '{}'".format(instruction))
        
        return operations


class PDFAssistantExecutor:
    """Ejecuta operaciones parsed en el documento PDF"""
    
    @staticmethod
    async def execute_delete_page(doc, pages: List[int]) -> None:
        """Ejecuta eliminación de páginas"""
        pages_sorted = sorted(pages, reverse=True)
        for page_num in pages_sorted:
            print("[CatFileAPI] [Executor] Eliminando página {}".format(page_num))
            doc.delete_page(page_num)
    
    @staticmethod
    async def execute_add_page(doc, position: int) -> None:
        """Ejecuta adición de página"""
        print("[CatFileAPI] [Executor] Añadiendo página en posición {}".format(position))
        doc.insert_page(position)
    
    @staticmethod
    async def execute_reorder_pages(doc, order: List[int]) -> None:
        """Ejecuta reordenamiento de páginas"""
        print("[CatFileAPI] [Executor] Reordenando páginas: {}".format(order))
        doc.select(order)
    
    @staticmethod
    async def execute_edit_text(doc, old_text: str, new_text: str, page_num: int) -> None:
        import unicodedata
        
        def normalize(s):
            return unicodedata.normalize('NFD', s.lower()) \
                   .encode('ascii', 'ignore').decode('ascii')
        
        page = doc[page_num]
        
        # Intento 1: búsqueda exacta
        rects = page.search_for(old_text)
        
        # Intento 1.5: buscar variantes con acentos comunes en español
        if not rects:
            import unicodedata
            # Generar variantes del texto buscado
            variants = [old_text]
            
            # Mapa de caracteres sin acento a con acento
            accent_map = {
                'a': ['á'], 'e': ['é'], 'i': ['í'], 
                'o': ['ó'], 'u': ['ú', 'ü'], 'n': ['ñ']
            }
            
            # Extraer texto real del PDF y buscar coincidencia normalizada
            norm_search = normalize(old_text.strip())
            words_in_page = page.get_text("words")  # (x0, y0, x1, y1, word, ...)
            
            for word_data in words_in_page:
                word = word_data[4]
                if normalize(word.strip().lower()) == norm_search:
                    # Encontró la palabra real con su acento correcto
                    rect = pymupdf.Rect(word_data[0], word_data[1], 
                                        word_data[2], word_data[3])
                    rects.append(rect)
                    print("[CatFileAPI] [Executor] Variante encontrada: '{}' en {}".format(
                        word, rect))
        
        # Intento 2: búsqueda case-insensitive con PyMuPDF flags
        if not rects:
            rects = page.search_for(old_text, flags=pymupdf.TEXT_DEHYPHENATE)
        
        # Intento 3: fallback normalizando acentos - busca la palabra exacta
        if not rects:
            norm_search = normalize(old_text.strip())
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        span_text = span["text"].strip()
                        if not span_text:
                            continue
                        norm_span = normalize(span_text)
                        
                        # Verificar que norm_search aparece como palabra completa
                        norm_words_list = re.split(r'[^a-z0-9]', norm_span)
                        if norm_search in norm_words_list:
                            # Encontrar posición aproximada de la palabra
                            # usando el rect del span completo
                            bbox = span["bbox"]
                            span_rect = pymupdf.Rect(bbox)
                            
                            # Calcular rect proporcional de la palabra
                            words = span_text.split()
                            norm_words = [normalize(w) for w in words]
                            
                            if norm_search in norm_words:
                                word_idx = norm_words.index(norm_search)
                                total_chars = sum(len(w) for w in words)
                                if total_chars > 0:
                                    chars_before = sum(len(words[i]) + 1 for i in range(word_idx))
                                    word_chars = len(words[word_idx])
                                    ratio_start = chars_before / total_chars
                                    ratio_end = (chars_before + word_chars) / total_chars
                                    
                                    span_width = span_rect.x1 - span_rect.x0
                                    word_rect = pymupdf.Rect(
                                        span_rect.x0 + ratio_start * span_width,
                                        span_rect.y0,
                                        span_rect.x0 + ratio_end * span_width,
                                        span_rect.y1
                                    )
                                    rects.append(word_rect)
                                    print("[CatFileAPI] [Executor] Palabra '{}' encontrada en {}".format(
                                        span_text, word_rect))
                            break
        
        if not rects:
            raise ValueError("Texto '{}' no encontrado en página {}".format(
                old_text, page_num + 1))
        
        for rect in rects:
            # Obtener fontsize del span en esa área
            fontsize = 11
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        if pymupdf.Rect(span["bbox"]).intersects(rect):
                            fontsize = span["size"]
                            break
            
            # Detectar color de fondo
            try:
                clip = page.get_pixmap(clip=rect, alpha=False)
                pixel = clip.pixel(1, 1)
                if isinstance(pixel, int):
                    gray = pixel / 255.0
                    bg_color = (gray, gray, gray)
                else:
                    bg_color = tuple(c / 255.0 for c in pixel[:3])
            except:
                bg_color = (1, 1, 1)
            
            # Cubrir solo la palabra
            page.draw_rect(rect, color=bg_color, fill=bg_color)
            
            # Insertar nueva palabra
            page.insert_text(
                pymupdf.Point(rect.x0, rect.y1 - 1),
                new_text,
                fontsize=fontsize,
                color=(0, 0, 0)
            )
            print("[CatFileAPI] [Executor] '{}' → '{}' en {}".format(
                old_text, new_text, rect))

    @staticmethod
    async def execute_add_text(doc, text: str, page_num: int, x: float = 50,
                                y: float = 50, fontsize: float = 12,
                                color: str = "#000000") -> None:
        # Convertir hex "#RRGGBB" a tuple (r, g, b) que usa PyMuPDF (valores 0.0-1.0)
        color = color.lstrip("#")
        r = int(color[0:2], 16) / 255.0
        g = int(color[2:4], 16) / 255.0
        b = int(color[4:6], 16) / 255.0
        
        page = doc[page_num]
        point = pymupdf.Point(x, y)
        page.insert_text(point, text, fontsize=fontsize, color=(r, g, b))
        print("[CatFileAPI] [Executor] Texto '{}' insertado en página {} con color rgb({},{},{})".format(
            text, page_num + 1, r, g, b))

    @staticmethod
    async def execute_delete_image(doc, page_num: int, image_index: int) -> None:
        """Ejecuta eliminación de imagen"""
        page = doc[page_num]
        images = page.get_images(full=True)
        
        if image_index >= len(images):
            raise ValueError("Imagen {} no encontrada en página {}".format(image_index+1, page_num+1))
        
        xref = images[image_index][0]
        image_rects = page.get_image_rects(xref)
        
        if image_rects:
            try:
                pixmap = page.get_pixmap(alpha=False)
                pixel_data = pixmap.pixel(0, 0)
                
                if isinstance(pixel_data, int):
                    gray_val = pixel_data / 255.0
                    bg_color = (gray_val, gray_val, gray_val)
                else:
                    bg_color = tuple(c / 255.0 for c in pixel_data[:3])
            except:
                bg_color = (1, 1, 1)
            
            rect = image_rects[0]
            print("[CatFileAPI] [Executor] Eliminando imagen {} de página {}".format(
                image_index+1, page_num+1))
            page.draw_rect(rect, color=bg_color, fill=bg_color)


class PDFAssistantService:
    """Servicio centralizado para ejecutar operaciones PDF
    
    Proporciona métodos de alto nivel que:
    1. Reciben PDF bytes y parámetros
    2. Abren el documento
    3. Ejecutan la operación
    4. Cierran y retornan PDF modificado
    
    Esto asegura que todos los endpoints (manuales y asistente)
    usen exactamente la misma lógica.
    """
    
    executor = PDFAssistantExecutor()
    
    @staticmethod
    async def delete_page_service(pdf_content: bytes, pages: List[int]) -> bytes:
        """Servicio: Eliminar páginas"""
        doc = pymupdf.open(stream=pdf_content, filetype="pdf")
        await PDFAssistantService.executor.execute_delete_page(doc, pages)
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        return output.getvalue()
    
    @staticmethod
    async def add_page_service(pdf_content: bytes, position: int = -1) -> bytes:
        """Servicio: Añadir página"""
        doc = pymupdf.open(stream=pdf_content, filetype="pdf")
        await PDFAssistantService.executor.execute_add_page(doc, position)
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        return output.getvalue()
    
    @staticmethod
    async def reorder_pages_service(pdf_content: bytes, order: List[int]) -> bytes:
        """Servicio: Reordenar páginas"""
        doc = pymupdf.open(stream=pdf_content, filetype="pdf")
        await PDFAssistantService.executor.execute_reorder_pages(doc, order)
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        return output.getvalue()
    
    @staticmethod
    async def edit_text_service(pdf_content: bytes, old_text: str, new_text: str, 
                                page_num: int = 0) -> bytes:
        """Servicio: Editar texto"""
        doc = pymupdf.open(stream=pdf_content, filetype="pdf")
        await PDFAssistantService.executor.execute_edit_text(doc, old_text, new_text, page_num)
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        return output.getvalue()
    
    @staticmethod
    async def add_text_service(pdf_content: bytes, text: str,
                               page_num: int, x: float = 50,
                               y: float = 50, fontsize: float = 12,
                               color: str = "#000000") -> bytes:
        doc = pymupdf.open(stream=pdf_content, filetype="pdf")
        await PDFAssistantService.executor.execute_add_text(
            doc, text, page_num, x, y, fontsize, color)
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        return output.getvalue()
    
    @staticmethod
    async def delete_image_service(pdf_content: bytes, page_num: int, 
                                   image_index: int) -> bytes:
        """Servicio: Eliminar imagen"""
        doc = pymupdf.open(stream=pdf_content, filetype="pdf")
        await PDFAssistantService.executor.execute_delete_image(doc, page_num, image_index)
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        return output.getvalue()
    
    @staticmethod
    def get_doc_info(pdf_content: bytes) -> Dict[str, Any]:
        """Obtiene información del documento sin modificarlo"""
        doc = pymupdf.open(stream=pdf_content, filetype="pdf")
        info = {
            "total_pages": len(doc),
            "images_per_page": []
        }
        
        for page_num in range(len(doc)):
            images = doc[page_num].get_images()
            info["images_per_page"].append({
                "page": page_num + 1,
                "count": len(images)
            })
        
        doc.close()
        return info

pdf_storage = {}

@app.post("/pdf/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Sube un PDF y devuelve un ID para referenciarlo"""
    try:
        print("[CatFileAPI] Subiendo PDF: {}".format(file.filename))
        content = await file.read()
        pdf_id = str(uuid.uuid4())
        
        # Extraer texto del PDF
        doc = pymupdf.open(stream=content, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()
        
        # Guardar en memoria
        pdf_storage[pdf_id] = {
            "content": content,
            "text": full_text,
            "filename": file.filename
        }
        
        print("[CatFileAPI] PDF subido con ID: {}".format(pdf_id))
        return {"pdf_id": pdf_id, "filename": file.filename}
    except Exception as e:
        print("[CatFileAPI] Error en upload: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/chat")
async def chat_with_pdf(request: Request):
    """Chat con el PDF usando Gemini - recibe JSON desde Flutter"""
    try:
        import json
        import os
 
        body = await request.json()
        pdf_id  = body.get("pdf_id")
        message = body.get("message")
        history = body.get("history", [])  # Lista de {role, content} ya parseada
 
        print("[CatFileAPI] Chat request - PDF: {}, Message: {}".format(pdf_id, message))
 
        if not pdf_id or not message:
            raise HTTPException(status_code=400, detail="pdf_id y message son requeridos")
 
        if pdf_id not in pdf_storage:
            raise HTTPException(status_code=404, detail="PDF no encontrado. Vuelve a subir el archivo.")
 
        pdf_text = pdf_storage[pdf_id]["text"]
 
        # TODO: reemplazar búsqueda simple por Gemini cuando haya cuota disponible
        pdf_lower = pdf_text.lower()
        message_lower = message.lower().strip()
        idx = pdf_lower.find(message_lower)

        if idx >= 0:
            start = max(0, idx - 250)
            end = min(len(pdf_text), idx + len(message) + 250)
            snippet = pdf_text[start:end].strip()
            reply = snippet
        else:
            reply = "No encontré información relacionada con tu pregunta en el documento 🐾"
 
        print("[CatFileAPI] Chat response generado correctamente")
        return {"reply": reply, "pdf_id": pdf_id}
 
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] Error en chat: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/assistant")
async def pdf_assistant(
    file: UploadFile = File(...),
    instruction: str = Form(...)
):
    """Intérprete de instrucciones en lenguaje natural para operaciones PDF
    
    Usa Gemini AI para interpretar instrucciones y PDFAssistantService para ejecutarlas.
    
    Ejemplos:
    - "Elimina la página 5 y agrega una página en blanco al final."
    - "Cambia Juan por Omar"
    - "Reordena las páginas como 2,0,1"
    """
    try:
        import json
        print("[CatFileAPI] [Assistant] Nueva solicitud: {}".format(instruction))
 
        content = await file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
 
        # 1. Extraer texto del PDF para contexto
        print("[CatFileAPI] [Assistant] Extrayendo texto del PDF")
        pdf_text = ""
        for page in doc:
            pdf_text += page.get_text()
        total_pages = len(doc)
 
        parser = PDFAssistantParser(language="es")
        # TODO: reemplazar PDFAssistantParser por Gemini cuando haya cuota disponible
        operations = parser.parse(instruction, doc)
        doc.close()
        print("[CatFileAPI] [Assistant] Operaciones detectadas: {}".format(len(operations)))
        for i, op in enumerate(operations, 1):
            print("[CatFileAPI]   {}. {}".format(i, op))
        
        # 4. Ejecutar operaciones usando el servicio centralizado
        executed = []
        pdf_state = content
        
        for op in operations:
            op_type = op.get("operation")
            params = op.get("params", {})
            
            try:
                if op_type == "delete_page":
                    print("[CatFileAPI] [Assistant] Ejecutando: {}".format(op_type))
                    pdf_state = await PDFAssistantService.delete_page_service(pdf_state, params["pages"])
                    
                elif op_type == "add_page":
                    print("[CatFileAPI] [Assistant] Ejecutando: {}".format(op_type))
                    pdf_state = await PDFAssistantService.add_page_service(pdf_state, params["position"])
                    
                elif op_type == "reorder_pages":
                    print("[CatFileAPI] [Assistant] Ejecutando: {}".format(op_type))
                    pdf_state = await PDFAssistantService.reorder_pages_service(pdf_state, params["order"])
                    
                elif op_type == "add_text":
                    print("[CatFileAPI] [Assistant] Ejecutando: {}".format(op_type))
                    pdf_state = await PDFAssistantService.add_text_service(
                        pdf_state,
                        params["text"],
                        params["page_num"],
                        params.get("x", 50),
                        params.get("y", 50),
                        params.get("fontsize", 12)
                    )
                    
                elif op_type == "edit_text":
                    print("[CatFileAPI] [Assistant] Ejecutando: {}".format(op_type))
                    pdf_state = await PDFAssistantService.edit_text_service(
                        pdf_state, params["old_text"], params["new_text"], params["page_num"]
                    )
                
                executed.append({
                    "operation": op_type,
                    "status": "success"
                })
                print("[CatFileAPI] [Assistant] ✓ {}".format(op_type))
                
            except Exception as e:
                executed.append({
                    "operation": op_type,
                    "status": "error",
                    "error": str(e)
                })
                print("[CatFileAPI] [Assistant] ✗ {}: {}".format(op_type, str(e)))
                raise
        
        # 5. Retornar PDF modificado
        output = io.BytesIO(pdf_state)
        
        print("[CatFileAPI] [Assistant] Todas las operaciones completadas exitosamente: {}".format(explanation))
        
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=assistant_output.pdf",
                "X-Operations": json.dumps(executed),
                "X-Explanation": explanation
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] [Assistant] Error: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))