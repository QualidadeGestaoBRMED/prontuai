# app/core

Esta pasta deve conter configurações centrais e utilitários globais do projeto.

Sugestão de arquivos:
- `config.py`: Carregamento de variáveis de ambiente, paths, configurações globais.
- `logging.py`: Configuração do sistema de logging.
- `celery_app.py`: (Opcional) Inicialização do Celery para tarefas assíncronas.

Estes utilitários devem ser importados por serviços e rotas conforme necessário.
