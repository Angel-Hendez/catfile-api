import requests

url = "http://127.0.0.1:8000/pdf/reorder-pages"
with open(r"C:\Users\nomin\Downloads\Presentacion digital fisica 4.pdf", "rb") as f:
    response = requests.post(url,
        files={"file": f},
        data={"order": "[0,2,1,3,4,5,6,7,8]"}
    )
    print("Status:", response.status_code)
    if response.status_code == 200:
        with open("reordenado.pdf", "wb") as out:
            out.write(response.content)
        print("PDF guardado!")
    else:
        print("Error:", response.json())