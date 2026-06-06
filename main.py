
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse
import pymupdf
import io

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
        content = await file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        page = doc[page_num]
        search_text = old_text or ""
        if not search_text.strip():
            raise HTTPException(status_code=400, detail="old_text no puede estar vacío")

        def find_text_rect(page, text):
            # Primero intentamos usar search_for si es posible
            rects = page.search_for(text)
            if rects:
                return rects[0], 12

            normalized_text = text
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block["type"] != 0:
                    continue

                for line in block["lines"]:
                    spans = line["spans"]
                    line_text = "".join(span["text"] for span in spans)
                    start_index = line_text.find(normalized_text)
                    if start_index < 0:
                        continue

                    match_rects = []
                    sizes = []
                    offset = 0
                    match_end = start_index + len(normalized_text)
                    for span in spans:
                        span_text = span["text"]
                        span_start = offset
                        span_end = offset + len(span_text)
                        offset = span_end
                        if span_end <= start_index or span_start >= match_end:
                            continue
                        match_rects.append(pymupdf.Rect(span["bbox"]))
                        sizes.append(span.get("size", 12))

                    if match_rects:
                        found_rect = match_rects[0]
                        for r in match_rects[1:]:
                            found_rect |= r
                        fontsize = int(round(sum(sizes) / len(sizes))) if sizes else 12
                        return found_rect, fontsize

            return None, None

        found_rect, fontsize = find_text_rect(page, search_text)
        if not found_rect:
            raise HTTPException(status_code=404, detail="Texto no encontrado en el PDF")

        page.add_redact_annot(found_rect, fill=(1, 1, 1))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
        page.insert_textbox(
            found_rect,
            new_text,
            fontsize=fontsize,
            color=(0, 0, 0),
            align=0
        )
        
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
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
        print("[CatFileAPI] Iniciando eliminación de imagen - página: {}, índice: {}".format(page_num, image_index))
        content = await file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        if page_num >= len(doc):
            raise HTTPException(status_code=400, detail="Número de página inválido")
        
        page = doc[page_num]
        images = page.get_images(full=True)
        
        if image_index >= len(images):
            raise HTTPException(status_code=404, detail="Imagen no encontrada en el índice especificado")
        
        xref = images[image_index][0]
        print("[CatFileAPI] Eliminando imagen con xref: {}".format(xref))
        
        # Obtener el bbox de la imagen
        image_rects = page.get_image_rects(xref)
        if not image_rects:
            raise HTTPException(status_code=404, detail="No se pudo obtener el área de la imagen")
        
        rect = image_rects[0]
        print("[CatFileAPI] Área de imagen: {}".format(rect))
        
        # Detectar el color de fondo de la página
        try:
            pixmap = page.get_pixmap(alpha=False)
            # Muestrear el píxel en la esquina superior izquierda (0, 0)
            pixel_data = pixmap.pixel(0, 0)
            
            # Convertir el dato del píxel a RGB normalizado (0-1)
            if isinstance(pixel_data, int):
                # Escala de grises
                gray_val = pixel_data / 255.0
                bg_color = (gray_val, gray_val, gray_val)
            else:
                # RGB tuple
                bg_color = tuple(c / 255.0 for c in pixel_data[:3])
            
            print("[CatFileAPI] Color de fondo detectado: {}".format(bg_color))
        except:
            # Si no se puede detectar el color, usar blanco por defecto
            bg_color = (1, 1, 1)
            print("[CatFileAPI] No se pudo detectar color de fondo, usando blanco por defecto")
        
        # Dibujar un rectángulo con el color de fondo sobre la imagen
        page.draw_rect(rect, color=bg_color, fill=bg_color)
        print("[CatFileAPI] Rectángulo con color de fondo dibujado sobre la imagen")
        
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        
        print("[CatFileAPI] Imagen eliminada exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] Error en delete-image: {}".format(str(e)))
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
        print("[CatFileAPI] Iniciando eliminación de páginas: {}".format(pages))
        content = await file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        import json
        try:
            pages_to_delete = json.loads(pages)
        except:
            raise HTTPException(status_code=400, detail="Formato de páginas inválido. Debe ser JSON: '[0,2,5]'")
        
        # Ordenar en orden descendente para eliminar desde el final
        pages_to_delete = sorted(set(pages_to_delete), reverse=True)
        
        for page_num in pages_to_delete:
            if page_num < 0 or page_num >= len(doc):
                raise HTTPException(status_code=400, detail="Número de página {} fuera de rango".format(page_num))
            print("[CatFileAPI] Eliminando página {}".format(page_num))
            doc.delete_page(page_num)
        
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        
        print("[CatFileAPI] Páginas eliminadas exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] Error en delete-page: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/add-page")
async def add_page(
    file: UploadFile = File(...),
    position: int = Form(-1)
):
    """Añade una página en blanco al PDF (position=-1 al final)"""
    try:
        print("[CatFileAPI] Iniciando adición de página en blanco - posición: {}".format(position))
        content = await file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        # Obtener dimensiones de la primera página
        if len(doc) > 0:
            first_page = doc[0]
            width = first_page.rect.width
            height = first_page.rect.height
        else:
            width = 612
            height = 792
        
        new_rect = pymupdf.Rect(0, 0, width, height)
        
        if position < 0 or position >= len(doc):
            print("[CatFileAPI] Insertando página al final")
            doc.insert_page(-1)
        else:
            print("[CatFileAPI] Insertando página en posición {}".format(position))
            doc.insert_page(position)
        
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        
        print("[CatFileAPI] Página añadida exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] Error en add-page: {}".format(str(e)))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf/reorder-pages")
async def reorder_pages(
    file: UploadFile = File(...),
    order: str = Form(...)
):
    """Reordena las páginas del PDF (pasar como string JSON: '[2,0,1]')"""
    try:
        print("[CatFileAPI] Iniciando reordenamiento de páginas: {}".format(order))
        content = await file.read()
        doc = pymupdf.open(stream=content, filetype="pdf")
        
        import json
        try:
            new_order = json.loads(order)
        except:
            raise HTTPException(status_code=400, detail="Formato de orden inválido. Debe ser JSON: '[2,0,1]'")
        
        if len(new_order) != len(doc):
            raise HTTPException(status_code=400, detail="El número de páginas no coincide")
        
        if set(new_order) != set(range(len(doc))):
            raise HTTPException(status_code=400, detail="Los índices de página deben ser únicos y estar entre 0 y {}".format(len(doc)-1))
        
        print("[CatFileAPI] Aplicando nuevo orden: {}".format(new_order))
        doc.select(new_order)
        
        output = io.BytesIO()
        doc.save(output, garbage=4, deflate=True)
        doc.close()
        output.seek(0)
        
        print("[CatFileAPI] Páginas reordenadas exitosamente")
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=edited.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[CatFileAPI] Error en reorder-pages: {}".format(str(e)))
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