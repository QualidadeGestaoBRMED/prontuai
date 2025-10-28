# app/models

Esta pasta deve conter os modelos de dados (schemas) usados na API, utilizando Pydantic.

Sugestão de arquivos:
- `ocr.py`: Schemas para entrada/saída das rotas de OCR.
- `faq.py`: Schemas para entrada/saída das rotas de FAQ.
- `brmed.py`: Schemas para entrada/saída das rotas de BRMED.

Os modelos devem ser importados nas rotas para validação automática dos dados.


