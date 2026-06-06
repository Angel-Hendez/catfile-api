
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse
import pymupdf
import io
import uuid
import os

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
        """Ejecuta reemplazo de texto"""
        page = doc[page_num]
        rects = page.search_for(old_text)
        
        if not rects:
            raise ValueError("Texto '{}' no encontrado en página {}".format(old_text, page_num+1))
        
        for rect in rects:
            print("[CatFileAPI] [Executor] Reemplazando '{}' por '{}' en página {}".format(
                old_text, new_text, page_num+1))
            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
            page.insert_textbox(rect, new_text, fontsize=12, color=(0, 0, 0), align=0)
    
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
async def chat_with_pdf(
    pdf_id: str = Form(...),
    message: str = Form(...),
    history: str = Form("[]")
):
    """Chat con el PDF usando Gemini"""
    try:
        import json
        import httpx
        
        print("[CatFileAPI] Chat request - PDF: {}, Message: {}".format(pdf_id, message))
        
        if pdf_id not in pdf_storage:
            raise HTTPException(status_code=404, detail="PDF no encontrado")
        
        pdf_text = pdf_storage[pdf_id]["text"]
        chat_history = json.loads(history)
        
        # Construir prompt para Gemini
        system_prompt = """Eres Catfile 🐾, un asistente profesional que ayuda a los usuarios a entender y editar sus documentos PDF.
        
El documento que debes analizar es el siguiente:

{}""".format(pdf_text[:50000])  # Limitar texto
        
        messages = [{"role": "user", "content": system_prompt}]
        for h in chat_history:
            messages.append(h)
        messages.append({"role": "user", "content": message})
        
        # Llamar a Gemini
        import os
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={}".format(gemini_key),
                json={
                    "contents": [{"parts": [{"text": msg["content"]}], "role": msg["role"] if msg["role"] == "user" else "model"} for msg in messages],
                    "generationConfig": {"maxOutputTokens": 1000}
                }
            )
        
        result = response.json()
        reply = result["candidates"][0]["content"]["parts"][0]["text"]
        
        print("[CatFileAPI] Chat response generated")
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
    
    Usa exactamente la misma lógica que los endpoints manuales a través de PDFAssistantService.
    
    Ejemplos:
    - "Elimina la página 5 y agrega una página en blanco al final."
    - "Cambia Juan por Omar y elimina la imagen principal."
    - "Reemplaza contrato por convenio."
    """
    try:
        print("[CatFileAPI] [Assistant] Nueva solicitud: {}".format(instruction))
        
        content = await file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        # 1. Parsear instrucción
        parser = PDFAssistantParser(language="es")
        operations = parser.parse(instruction, doc)
        
        print("[CatFileAPI] [Assistant] Operaciones detectadas: {}".format(len(operations)))
        for i, op in enumerate(operations, 1):
            print("[CatFileAPI]   {}. {}".format(i, op["description"]))
        
        doc.close()
        
        # 2. Ejecutar operaciones usando el servicio centralizado
        executed = []
        pdf_state = content
        
        for op in operations:
            op_type = op["operation"]
            params = op["params"]
            
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
                    
                elif op_type == "edit_text":
                    print("[CatFileAPI] [Assistant] Ejecutando: {}".format(op_type))
                    pdf_state = await PDFAssistantService.edit_text_service(
                        pdf_state, params["old_text"], params["new_text"], params["page_num"]
                    )
                    
                elif op_type == "delete_image":
                    print("[CatFileAPI] [Assistant] Ejecutando: {}".format(op_type))
                    pdf_state = await PDFAssistantService.delete_image_service(
                        pdf_state, params["page_num"], params["image_index"]
                    )
                    
                elif op_type == "get_text":
                    # Solo consulta, no modifica
                    print("[CatFileAPI] [Assistant] get_text - solo consulta")
                    pass
                    
                elif op_type == "get_images":
                    # Solo consulta, no modifica
                    print("[CatFileAPI] [Assistant] get_images - solo consulta")
                    pass
                    
                elif op_type == "add_signature":
                    return {
                        "error": True,
                        "message": "Para añadir firma, usa el endpoint /pdf/add-signature directamente",
                        "operations": operations
                    }
                
                executed.append({
                    "operation": op_type,
                    "status": "success",
                    "description": op["description"]
                })
                print("[CatFileAPI] [Assistant] ✓ {}".format(op_type))
                
            except Exception as e:
                executed.append({
                    "operation": op_type,
                    "status": "error",
                    "error": str(e),
                    "description": op["description"]
                })
                print("[CatFileAPI] [Assistant] ✗ {}: {}".format(op_type, str(e)))
                raise
        
        # 3. Retornar PDF modificado
        output = io.BytesIO(pdf_state)
        
        print("[CatFileAPI] [Assistant] Todas las operaciones completadas exitosamente")
        
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=assistant_output.pdf",
                "X-Operations": json.dumps(executed)
            }
        )
        
    except ValueError as e:
        print("[CatFileAPI] [Assistant] Error de validación: {}".format(str(e)))
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] [Assistant] Error: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))