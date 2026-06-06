[1mdiff --git a/main.py b/main.py[m
[1mindex 4bd6cfe..d34de0c 100644[m
[1m--- a/main.py[m
[1m+++ b/main.py[m
[36m@@ -51,75 +51,22 @@[m [masync def edit_pdf_text([m
 ):[m
     """Reemplaza texto en un PDF"""[m
     try:[m
[32m+[m[32m        print("[CatFileAPI] EDIT-TEXT: Iniciando edición de texto - página: {}".format(page_num))[m
         content = await file.read()[m
[31m-        doc = pymupdf.open(stream=content, filetype="pdf")[m
         [m
[31m-        page = doc[page_num][m
[31m-        search_text = old_text or ""[m
[31m-        if not search_text.strip():[m
[32m+[m[32m        if not old_text.strip():[m
             raise HTTPException(status_code=400, detail="old_text no puede estar vacío")[m
[31m-[m
[31m-        def find_text_rect(page, text):[m
[31m-            # Primero intentamos usar search_for si es posible[m
[31m-            rects = page.search_for(text)[m
[31m-            if rects:[m
[31m-                return rects[0], 12[m
[31m-[m
[31m-            normalized_text = text[m
[31m-            blocks = page.get_text("dict")["blocks"][m
[31m-            for block in blocks:[m
[31m-                if block["type"] != 0:[m
[31m-                    continue[m
[31m-[m
[31m-                for line in block["lines"]:[m
[31m-                    spans = line["spans"][m
[31m-                    line_text = "".join(span["text"] for span in spans)[m
[31m-                    start_index = line_text.find(normalized_text)[m
[31m-                    if start_index < 0:[m
[31m-                        continue[m
[31m-[m
[31m-                    match_rects = [][m
[31m-                    sizes = [][m
[31m-                    offset = 0[m
[31m-                    match_end = start_index + len(normalized_text)[m
[31m-                    for span in spans:[m
[31m-                        span_text = span["text"][m
[31m-                        span_start = offset[m
[31m-                        span_end = offset + len(span_text)[m
[31m-                        offset = span_end[m
[31m-                        if span_end <= start_index or span_start >= match_end:[m
[31m-                            continue[m
[31m-                        match_rects.append(pymupdf.Rect(span["bbox"]))[m
[31m-                        sizes.append(span.get("size", 12))[m
[31m-[m
[31m-                    if match_rects:[m
[31m-                        found_rect = match_rects[0][m
[31m-                        for r in match_rects[1:]:[m
[31m-                            found_rect |= r[m
[31m-                        fontsize = int(round(sum(sizes) / len(sizes))) if sizes else 12[m
[31m-                        return found_rect, fontsize[m
[31m-[m
[31m-            return None, None[m
[31m-[m
[31m-        found_rect, fontsize = find_text_rect(page, search_text)[m
[31m-        if not found_rect:[m
[31m-            raise HTTPException(status_code=404, detail="Texto no encontrado en el PDF")[m
[31m-[m
[31m-        page.add_redact_annot(found_rect, fill=(1, 1, 1))[m
[31m-        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)[m
[31m-        page.insert_textbox([m
[31m-            found_rect,[m
[31m-            new_text,[m
[31m-            fontsize=fontsize,[m
[31m-            color=(0, 0, 0),[m
[31m-            align=0[m
[31m-        )[m
         [m
[31m-        output = io.BytesIO()[m
[31m-        doc.save(output, garbage=4, deflate=True)[m
[31m-        doc.close()[m
[31m-        output.seek(0)[m
[32m+[m[32m        # Validar con la información del documento[m
[32m+[m[32m        doc_info = PDFAssistantService.get_doc_info(content)[m
[32m+[m[32m        if page_num >= doc_info["total_pages"]:[m
[32m+[m[32m            raise HTTPException(status_code=400, detail="Página {} fuera de rango".format(page_num))[m
[32m+[m[41m        [m
[32m+[m[32m        # Usar el servicio centralizado[m
[32m+[m[32m        pdf_bytes = await PDFAssistantService.edit_text_service(content, old_text, new_text, page_num)[m
         [m
[32m+[m[32m        output = io.BytesIO(pdf_bytes)[m
[32m+[m[32m        print("[CatFileAPI] EDIT-TEXT: Completado exitosamente")[m
         return StreamingResponse([m
             output,[m
             media_type="application/pdf",[m
[36m@@ -128,6 +75,7 @@[m [masync def edit_pdf_text([m
     except HTTPException:[m
         raise[m
     except Exception as e:[m
[32m+[m[32m        print("[CatFileAPI] EDIT-TEXT: Error - {}".format(str(e)))[m
         raise HTTPException(status_code=500, detail=str(e))[m
 [m
 [m
[36m@@ -278,61 +226,19 @@[m [masync def delete_image([m
 ):[m
     """Elimina una imagen del PDF"""[m
     try:[m
[31m-        print("[CatFileAPI] Iniciando eliminación de imagen - página: {}, índice: {}".format(page_num, image_index))[m
[32m+[m[32m        print("[CatFileAPI] DELETE-IMAGE: Iniciando eliminación - página: {}, índice: {}".format(page_num, image_index))[m
         content = await file.read()[m
[31m-        doc = pymupdf.open(stream=content, filetype="pdf")[m
[31m-        [m
[31m-        if page_num >= len(doc):[m
[31m-            raise HTTPException(status_code=400, detail="Número de página inválido")[m
         [m
[31m-        page = doc[page_num][m
[31m-        images = page.get_images(full=True)[m
[32m+[m[32m        # Validar con la información del documento[m
[32m+[m[32m        doc_info = PDFAssistantService.get_doc_info(content)[m
[32m+[m[32m        if page_num >= doc_info["total_pages"]:[m
[32m+[m[32m            raise HTTPException(status_code=400, detail="Página {} fuera de rango".format(page_num))[m
         [m
[31m-        if image_index >= len(images):[m
[31m-            raise HTTPException(status_code=404, detail="Imagen no encontrada en el índice especificado")[m
[32m+[m[32m        # Usar el servicio centralizado[m
[32m+[m[32m        pdf_bytes = await PDFAssistantService.delete_image_service(content, page_num, image_index)[m
         [m
[31m-        xref = images[image_index][0][m
[31m-        print("[CatFileAPI] Eliminando imagen con xref: {}".format(xref))[m
[31m-        [m
[31m-        # Obtener el bbox de la imagen[m
[31m-        image_rects = page.get_image_rects(xref)[m
[31m-        if not image_rects:[m
[31m-            raise HTTPException(status_code=404, detail="No se pudo obtener el área de la imagen")[m
[31m-        [m
[31m-        rect = image_rects[0][m
[31m-        print("[CatFileAPI] Área de imagen: {}".format(rect))[m
[31m-        [m
[31m-        # Detectar el color de fondo de la página[m
[31m-        try:[m
[31m-            pixmap = page.get_pixmap(alpha=False)[m
[31m-            # Muestrear el píxel en la esquina superior izquierda (0, 0)[m
[31m-            pixel_data = pixmap.pixel(0, 0)[m
[31m-            [m
[31m-            # Convertir el dato del píxel a RGB normalizado (0-1)[m
[31m-            if isinstance(pixel_data, int):[m
[31m-                # Escala de grises[m
[31m-                gray_val = pixel_data / 255.0[m
[31m-                bg_color = (gray_val, gray_val, gray_val)[m
[31m-            else:[m
[31m-                # RGB tuple[m
[31m-                bg_color = tuple(c / 255.0 for c in pixel_data[:3])[m
[31m-            [m
[31m-            print("[CatFileAPI] Color de fondo detectado: {}".format(bg_color))[m
[31m-        except:[m
[31m-            # Si no se puede detectar el color, usar blanco por defecto[m
[31m-            bg_color = (1, 1, 1)[m
[31m-            print("[CatFileAPI] No se pudo detectar color de fondo, usando blanco por defecto")[m
[31m-        [m
[31m-        # Dibujar un rectángulo con el color de fondo sobre la imagen[m
[31m-        page.draw_rect(rect, color=bg_color, fill=bg_color)[m
[31m-        print("[CatFileAPI] Rectángulo con color de fondo dibujado sobre la imagen")[m
[31m-        [m
[31m-        output = io.BytesIO()[m
[31m-        doc.save(output, garbage=4, deflate=True)[m
[31m-        doc.close()[m
[31m-        output.seek(0)[m
[31m-        [m
[31m-        print("[CatFileAPI] Imagen eliminada exitosamente")[m
[32m+[m[32m        output = io.BytesIO(pdf_bytes)[m
[32m+[m[32m        print("[CatFileAPI] DELETE-IMAGE: Completado exitosamente")[m
         return StreamingResponse([m
             output,[m
             media_type="application/pdf",[m
[36m@@ -341,7 +247,7 @@[m [masync def delete_image([m
     except HTTPException:[m
         raise[m
     except Exception as e:[m
[31m-        print("[CatFileAPI] Error en delete-image: {}".format(str(e)))[m
[32m+[m[32m        print("[CatFileAPI] DELETE-IMAGE: Error - {}".format(str(e)))[m
         raise HTTPException(status_code=500, detail=str(e))[m
 [m
 [m
[36m@@ -398,9 +304,8 @@[m [masync def delete_page([m
 ):[m
     """Elimina páginas del PDF (pasar como string JSON: '[0,2,5]')"""[m
     try:[m
[31m-        print("[CatFileAPI] Iniciando eliminación de páginas: {}".format(pages))[m
[32m+[m[32m        print("[CatFileAPI] DELETE-PAGE: Iniciando eliminación de páginas: {}".format(pages))[m
         content = await file.read()[m
[31m-        doc = pymupdf.open(stream=content, filetype="pdf")[m
         [m
         import json[m
         try:[m
[36m@@ -408,21 +313,18 @@[m [masync def delete_page([m
         except:[m
             raise HTTPException(status_code=400, detail="Formato de páginas inválido. Debe ser JSON: '[0,2,5]'")[m
         [m
[31m-        # Ordenar en orden descendente para eliminar desde el final[m
[31m-        pages_to_delete = sorted(set(pages_to_delete), reverse=True)[m
[31m-        [m
[32m+[m[32m        # Validar con la información del documento[m
[32m+[m[32m        doc_info = PDFAssistantService.get_doc_info(content)[m
         for page_num in pages_to_delete:[m
[31m-            if page_num < 0 or page_num >= len(doc):[m
[31m-                raise HTTPException(status_code=400, detail="Número de página {} fuera de rango".format(page_num))[m
[31m-            print("[CatFileAPI] Eliminando página {}".format(page_num))[m
[31m-            doc.delete_page(page_num)[m
[32m+[m[32m            if page_num < 0 or page_num >= doc_info["total_pages"]:[m
[32m+[m[32m                raise HTTPException(status_code=400, detail="Página {} fuera de rango (0-{})".format([m
[32m+[m[32m                    page_num, doc_info["total_pages"]-1))[m
         [m
[31m-        output = io.BytesIO()[m
[31m-        doc.save(output, garbage=4, deflate=True)[m
[31m-        doc.close()[m
[31m-        output.seek(0)[m
[32m+[m[32m        # Usar el servicio centralizado[m
[32m+[m[32m        pdf_bytes = await PDFAssistantService.delete_page_service(content, pages_to_delete)[m
         [m
[31m-        print("[CatFileAPI] Páginas eliminadas exitosamente")[m
[32m+[m[32m        output = io.BytesIO(pdf_bytes)[m
[32m+[m[32m        print("[CatFileAPI] DELETE-PAGE: Completado exitosamente")[m
         return StreamingResponse([m
             output,[m
             media_type="application/pdf",[m
[36m@@ -431,7 +333,7 @@[m [masync def delete_page([m
     except HTTPException:[m
         raise[m
     except Exception as e:[m
[31m-        print("[CatFileAPI] Error en delete-page: {}".format(str(e)))[m
[32m+[m[32m        print("[CatFileAPI] DELETE-PAGE: Error - {}".format(str(e)))[m
         raise HTTPException(status_code=500, detail=str(e))[m
 [m
 [m
[36m@@ -442,34 +344,14 @@[m [masync def add_page([m
 ):[m
     """Añade una página en blanco al PDF (position=-1 al final)"""[m
     try:[m
[31m-        print("[CatFileAPI] Iniciando adición de página en blanco - posición: {}".format(position))[m
[32m+[m[32m        print("[CatFileAPI] ADD-PAGE: Iniciando adición de página - posición: {}".format(position))[m
         content = await file.read()[m
[31m-        doc = pymupdf.open(stream=content, filetype="pdf")[m
         [m
[31m-        # Obtener dimensiones de la primera página[m
[31m-        if len(doc) > 0:[m
[31m-            first_page = doc[0][m
[31m-            width = first_page.rect.width[m
[31m-            height = first_page.rect.height[m
[31m-        else:[m
[31m-            width = 612[m
[31m-            height = 792[m
[32m+[m[32m        # Usar el servicio centralizado[m
[32m+[m[32m        pdf_bytes = await PDFAssistantService.add_page_service(content, position)[m
         [m
[31m-        new_rect = pymupdf.Rect(0, 0, width, height)[m
[31m-        [m
[31m-        if position < 0 or position >= len(doc):[m
[31m-            print("[CatFileAPI] Insertando página al final")[m
[31m-            doc.insert_page(-1)[m
[31m-        else:[m
[31m-            print("[CatFileAPI] Insertando página en posición {}".format(position))[m
[31m-            doc.insert_page(position)[m
[31m-        [m
[31m-        output = io.BytesIO()[m
[31m-        doc.save(output, garbage=4, deflate=True)[m
[31m-        doc.close()[m
[31m-        output.seek(0)[m
[31m-        [m
[31m-        print("[CatFileAPI] Página añadida exitosamente")[m
[32m+[m[32m        output = io.BytesIO(pdf_bytes)[m
[32m+[m[32m        print("[CatFileAPI] ADD-PAGE: Completado exitosamente")[m
         return StreamingResponse([m
             output,[m
             media_type="application/pdf",[m
[36m@@ -478,7 +360,7 @@[m [masync def add_page([m
     except HTTPException:[m
         raise[m
     except Exception as e:[m
[31m-        print("[CatFileAPI] Error en add-page: {}".format(str(e)))[m
[32m+[m[32m        print("[CatFileAPI] ADD-PAGE: Error - {}".format(str(e)))[m
         raise HTTPException(status_code=500, detail=str(e))[m
 [m
 [m
[36m@@ -489,9 +371,8 @@[m [masync def reorder_pages([m
 ):[m
     """Reordena las páginas del PDF (pasar como string JSON: '[2,0,1]')"""[m
     try:[m
[31m-        print("[CatFileAPI] Iniciando reordenamiento de páginas: {}".format(order))[m
[32m+[m[32m        print("[CatFileAPI] REORDER-PAGES: Iniciando reordenamiento - {}".format(order))[m
         content = await file.read()[m
[31m-        doc = pymupdf.open(stream=content, filetype="pdf")[m
         [m
         import json[m
         try:[m
[36m@@ -499,21 +380,21 @@[m [masync def reorder_pages([m
         except:[m
             raise HTTPException(status_code=400, detail="Formato de orden inválido. Debe ser JSON: '[2,0,1]'")[m
         [m
[31m-        if len(new_order) != len(doc):[m
[31m-            raise HTTPException(status_code=400, detail="El número de páginas no coincide")[m
[32m+[m[32m        # Validar con la información del documento[m
[32m+[m[32m        doc_info = PDFAssistantService.get_doc_info(content)[m
         [m
[31m-        if set(new_order) != set(range(len(doc))):[m
[31m-            raise HTTPException(status_code=400, detail="Los índices de página deben ser únicos y estar entre 0 y {}".format(len(doc)-1))[m
[32m+[m[32m        if len(new_order) != doc_info["total_pages"]:[m
[32m+[m[32m            raise HTTPException(status_code=400, detail="El número de páginas no coincide")[m
         [m
[31m-        print("[CatFileAPI] Aplicando nuevo orden: {}".format(new_order))[m
[31m-        doc.select(new_order)[m
[32m+[m[32m        if set(new_order) != set(range(doc_info["total_pages"])):[m
[32m+[m[32m            raise HTTPException(status_code=400, detail="Los índices de página deben ser únicos y estar entre 0 y {}".format([m
[32m+[m[32m                doc_info["total_pages"]-1))[m
         [m
[31m-        output = io.BytesIO()[m
[31m-        doc.save(output, garbage=4, deflate=True)[m
[31m-        doc.close()[m
[31m-        output.seek(0)[m
[32m+[m[32m        # Usar el servicio centralizado[m
[32m+[m[32m        pdf_bytes = await PDFAssistantService.reorder_pages_service(content, new_order)[m
         [m
[31m-        print("[CatFileAPI] Páginas reordenadas exitosamente")[m
[32m+[m[32m        output = io.BytesIO(pdf_bytes)[m
[32m+[m[32m        print("[CatFileAPI] REORDER-PAGES: Completado exitosamente")[m
         return StreamingResponse([m
             output,[m
             media_type="application/pdf",[m
[36m@@ -522,7 +403,7 @@[m [masync def reorder_pages([m
     except HTTPException:[m
         raise[m
     except Exception as e:[m
[31m-        print("[CatFileAPI] Error en reorder-pages: {}".format(str(e)))[m
[32m+[m[32m        print("[CatFileAPI] REORDER-PAGES: Error - {}".format(str(e)))[m
         raise HTTPException(status_code=500, detail=str(e))[m
 [m
 [m
[36m@@ -573,4 +454,519 @@[m [masync def get_images([m
         raise[m
     except Exception as e:[m
         print("[CatFileAPI] Error en get-images: {}".format(str(e)))[m
[32m+[m[32m        raise HTTPException(status_code=500, detail=str(e))[m
[32m+[m
[32m+[m
[32m+[m[32m# =====================================================[m
[32m+[m[32m# MÓDULO ASISTENTE: Parser de Instrucciones Naturales[m
[32m+[m[32m# =====================================================[m
[32m+[m
[32m+[m[32mimport re[m
[32m+[m[32mimport json[m
[32m+[m[32mfrom typing import List, Dict, Any, Tuple[m
[32m+[m
[32m+[m[32mclass PDFAssistantParser:[m
[32m+[m[32m    """Parser de instrucciones en lenguaje natural para operaciones PDF"""[m
[32m+[m[41m    [m
[32m+[m[32m    def __init__(self, language="es"):[m
[32m+[m[32m        self.language = language[m
[32m+[m[32m        self.doc = None  # Se asigna cuando se procesa[m
[32m+[m[41m        [m
[32m+[m[32m        # Patrones en español[m
[32m+[m[32m        self.patterns_es = {[m
[32m+[m[32m            "delete_page": r"(?:elimina|borra|quita|remueve)\s+(?:la\s+)?p[áa]gina[s]?\s+(\d+(?:\s*,\s*\d+)*|\[[\d\s,]+\])",[m
[32m+[m[32m            "add_page": r"(?:a[ñn]ade|agrega|inserta)\s+(?:una\s+)?p[áa]gina\s+(?:en\s+blanco\s+)?(?:al\s+)?(?:final|final|final de documento)",[m
[32m+[m[32m            "add_page_position": r"(?:a[ñn]ade|agrega|inserta)\s+(?:una\s+)?p[áa]gina\s+(?:en\s+blanco\s+)?(?:en\s+)?(?:posici[óo]n|posición)\s+(\d+)",[m
[32m+[m[32m            "reorder_pages": r"(?:reordena|ordena|reorganiza)\s+las\s+p[áa]ginas\s+(?:como|en|en el orden)\s+(.+?)(?:\.|$)",[m
[32m+[m[32m            "edit_text": r"(?:cambia|reemplaza|sustituye|remplaza)\s+['\"]?([^'\"]+)['\"]?\s+(?:por|con)\s+['\"]?([^'\"]+)['\"]?",[m
[32m+[m[32m            "delete_image": r"(?:elimina|borra|quita)\s+(?:la\s+)?(?:imagen|foto|gr[áa]fico)\s+(?:principal|n[úu]mero\s+)?(\d+)?",[m
[32m+[m[32m            "add_image": r"(?:a[ñn]ade|agrega|inserta)\s+(?:una\s+)?(?:imagen|foto|gr[áa]fico)",[m
[32m+[m[32m            "add_signature": r"(?:a[ñn]ade|agrega|inserta)\s+(?:una\s+)?firma",[m
[32m+[m[32m            "move_image": r"(?:mueve|desplaza|posiciona)\s+(?:la\s+)?(?:imagen|foto|gr[áa]fico)\s+(?:a\s+)?(\(?\d+\s*,\s*\d+\)?)",[m
[32m+[m[32m            "get_text": r"(?:obtén|obtiene|extrae|saca)\s+(?:el\s+)?(?:texto|contenido|informaci[óo]n)",[m
[32m+[m[32m            "get_images": r"(?:obtén|obtiene|extrae|lista|muestra)\s+(?:todas?\s+)?(?:las\s+)?(?:imágenes|fotos|gr[áa]ficos)",[m
[32m+[m[32m        }[m
[32m+[m[41m        [m
[32m+[m[32m        # Patrones en inglés (para futuro)[m
[32m+[m[32m        self.patterns_en = {[m
[32m+[m[32m            "delete_page": r"(?:delete|remove|drop|erase)\s+(?:the\s+)?pages?\s+(\d+(?:\s*,\s*\d+)*|\[[\d\s,]+\])",[m
[32m+[m[32m            "add_page": r"(?:add|insert|create)\s+(?:a\s+)?(?:blank\s+)?page\s+(?:at\s+)?(?:the\s+end|end)",[m
[32m+[m[32m            "edit_text": r"(?:change|replace|substitute|swap)\s+['\"]?([^'\"]+)['\"]?\s+(?:with|for)\s+['\"]?([^'\"]+)['\"]?",[m
[32m+[m[32m            "delete_image": r"(?:delete|remove|erase)\s+(?:the\s+)?(?:image|picture|graphic)\s+(?:number\s+)?(\d+)?",[m
[32m+[m[32m            "add_signature": r"(?:add|insert|place)\s+(?:a\s+)?(?:signature|sign)",[m
[32m+[m[32m        }[m
[32m+[m[41m        [m
[32m+[m[32m        self.patterns = self.patterns_es if language == "es" else self.patterns_en[m
[32m+[m[41m    