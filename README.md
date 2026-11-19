# Lab App — Aplicação com Redis

Aplicação web simples para gerenciamento de itens, desenvolvida para demonstrar o uso de um banco de dados NoSQL **Redis** com uma API Python e uma interface web. O projeto implementa operações de criação, consulta, atualização e exclusão (CRUD), além de um índice ordenado por data de criação.

<video src="videos/video.mp4" controls width="640"></video>

## Objetivo

O objetivo do projeto é implementar individualmente uma solução que utilize um banco NoSQL diferente de um banco relacional tradicional, explorando estruturas de dados oferecidas pelo Redis e demonstrando como uma aplicação pode compartilhar os mesmos dados entre múltiplas instâncias de backend.

## Tecnologias

| Camada | Tecnologia | Responsabilidade |
|---|---|---|
| Banco de dados | Redis 7 | Armazenamento dos itens e índice por data |
| Backend | Python 3.12, FastAPI | API HTTP e regras de negócio |
| Cliente Redis | `redis` para Python (API assíncrona) | Comunicação assíncrona com o Redis |
| Validação | Pydantic | Validação dos dados de entrada e saída |
| Frontend | React 19, TypeScript e Vite | Interface de gerenciamento |
| Servidor web | Nginx | Entrega do frontend e proxy da API no ambiente local |
| Containers | Docker e Docker Compose | Execução dos serviços |

## Arquitetura

No ambiente local, o Docker Compose inicia três serviços:

- **frontend:** aplicação React compilada e servida pelo Nginx;
- **backend:** API FastAPI, que acessa o Redis;
- **redis:** banco de dados Redis 7.

O Nginx encaminha as requisições da interface para a API pelo caminho `/api/`. O backend acessa o Redis pela rede interna do Docker usando a variável `REDIS_URL`.

O serviço `backend` pode ser escalado com Docker Compose. As instâncias compartilham o mesmo serviço Redis, portanto os dados não ficam armazenados na memória isolada de cada processo da API.

## Modelagem dos dados no Redis

O projeto utiliza duas estruturas principais:

### 1. Hash — dados de cada item

Cada item é armazenado em uma chave própria, identificada por UUID:

```text
item:<uuid>
```

O Hash contém os campos:

| Campo | Tipo lógico | Descrição |
|---|---|---|
| `name` | texto | Nome do item |
| `description` | texto | Descrição opcional |
| `done` | texto (`1` ou `0`) | Indica se o item foi concluído |
| `created_at` | data/hora ISO 8601 | Data de criação |
| `updated_at` | data/hora ISO 8601 | Data da última atualização |

O Redis armazena os valores do Hash como strings. Por isso, o backend converte valores booleanos para `"1"` e `"0"` antes de gravar e os converte novamente ao montar a resposta da API.

### 2. Sorted Set — índice por data

A chave `items:by_date` é um Sorted Set. Cada membro é o UUID de um item e sua pontuação (*score*) é o timestamp de criação:

```text
items:by_date
    membro: <uuid>
    score: timestamp de created_at
```

Isso permite listar os itens mais recentes primeiro usando `ZREVRANGE`, sem precisar ordenar todos os Hashes na aplicação quando não há filtro por status.

### Relação entre as estruturas

O Hash guarda os dados completos. O Sorted Set funciona como um índice que permite localizar e ordenar os identificadores. Ao criar ou excluir um item, o backend atualiza as duas estruturas na mesma transação Redis.

## Funcionalidades

- Criar item.
- Listar itens, com paginação (`skip` e `limit`).
- Filtrar itens pelo campo `done`.
- Consultar um item pelo UUID.
- Substituir os dados de um item com `PUT`.
- Atualizar parcialmente um item com `PATCH`.
- Excluir um item.
- Verificar a saúde da API (`/api/health`).
- Verificar a conexão com o Redis (`/api/db-health`).
- Identificar informações do servidor que respondeu (`/api/whoami`).

## Endpoints da API

A API utiliza o prefixo `/api`.

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/health` | Verifica se a API está respondendo |
| `GET` | `/api/db-health` | Executa `PING` no Redis |
| `GET` | `/api/whoami` | Retorna informações do container/servidor |
| `POST` | `/api/items` | Cria um item |
| `GET` | `/api/items` | Lista itens |
| `GET` | `/api/items/{item_id}` | Consulta um item |
| `PUT` | `/api/items/{item_id}` | Substitui os campos do item |
| `PATCH` | `/api/items/{item_id}` | Atualiza somente os campos enviados |
| `DELETE` | `/api/items/{item_id}` | Exclui um item |

### Exemplo de criação

Requisição:

```http
POST /api/items
Content-Type: application/json
```

```json
{
  "name": "Estudar Redis",
  "description": "Entender Hash e Sorted Set",
  "done": false
}
```

A API gera o UUID e as datas de criação e atualização. O registro é gravado no Hash `item:<uuid>` e seu identificador é adicionado ao Sorted Set `items:by_date`.

### Validações

O backend valida os dados com Pydantic:

- `name`: obrigatório, entre 1 e 100 caracteres;
- `description`: opcional, até 500 caracteres;
- `done`: booleano, padrão `false`;
- `skip`: inteiro maior ou igual a zero;
- `limit`: inteiro entre 1 e 500.

IDs que não sejam UUID válidos são tratados como item não encontrado.

## Decisões de implementação

### Operações agrupadas com pipeline

Na criação, o `HSET` do item e o `ZADD` do índice são executados em um pipeline com transação (`transaction=True`). Na exclusão, o `DELETE` do Hash e o `ZREM` do índice também são agrupados em uma transação. Isso evita que apenas uma das duas estruturas seja atualizada em uma operação bem-sucedida.

### Atualização condicional com Lua

O backend registra um script Lua que primeiro verifica se a chave do item existe. Se não existir, retorna `0`; caso exista, executa `HSET` e retorna `1`.

Essa verificação e atualização acontecem no próprio Redis como uma operação de script, evitando que uma atualização recrie acidentalmente um item que já foi excluído.

### Consulta em lote

Para buscar os Hashes de vários IDs, o backend utiliza pipeline com `transaction=False`, reduzindo o número de idas e voltas entre a API e o Redis.

### Filtro por status

Quando não há filtro `done`, o backend usa diretamente o Sorted Set para obter somente o intervalo solicitado. Quando há filtro por `done`, o código lê os IDs do índice, busca os Hashes e filtra os registros na aplicação.

Essa segunda estratégia é simples para um conjunto pequeno de dados, mas pode ficar custosa à medida que o volume cresce, pois percorre todos os itens antes de aplicar a paginação.

## Como executar localmente

### Pré-requisitos

- Docker instalado;
- Docker Compose disponível pelo comando `docker compose`.

### Subir a aplicação

Na raiz do repositório, execute:

```bash
docker compose up --build
```

Acesse a aplicação em:

```text
http://localhost:8080
```

### Executar com duas réplicas do backend

```bash
docker compose up --build --scale backend=2
```

As réplicas compartilham o mesmo Redis. A aplicação também disponibiliza a opção **“Qual servidor está respondendo?”**, que consulta `/api/whoami` para exibir informações do container que respondeu.

### Parar a aplicação

```bash
docker compose down
```

Esse comando remove os containers, mas preserva o volume de dados do Redis.

Para remover também o volume e apagar os dados persistidos:

```bash
docker compose down -v
```

> Atenção: `down -v` apaga os dados armazenados no volume `redis-data`.

## Inspecionar os dados diretamente no Redis

Com os serviços em execução, abra o terminal do Redis:

```bash
docker compose exec redis redis-cli
```

Listar os IDs do índice, dos mais recentes para os mais antigos:

```redis
ZREVRANGE items:by_date 0 -1
```

Consultar os campos de um item:

```redis
HGETALL item:<uuid>
```

Verificar a conexão:

```redis
PING
```

## Vantagens do Redis observadas no projeto

- **Estruturas de dados especializadas:** Hash e Sorted Set atendem diretamente às necessidades de armazenar os campos e manter um índice ordenado.
- **Operações rápidas em memória:** o Redis é projetado para acesso de baixa latência, pois mantém os dados em memória.
- **Operações atômicas:** transações e scripts Lua ajudam a agrupar operações e proteger regras de atualização.
- **Compartilhamento entre instâncias:** várias instâncias da API podem acessar o mesmo conjunto de dados no Redis.
- **Persistência configurável:** o projeto habilita AOF (`appendonly yes`) e utiliza um volume Docker para manter os arquivos de dados.

## Desvantagens e limitações

- **Uso de memória:** manter os dados em memória pode exigir planejamento de capacidade e custo conforme o volume cresce.
- **Consultas menos flexíveis:** Redis não oferece consultas relacionais e filtros arbitrários como um banco SQL. No projeto, o filtro `done` precisa buscar os registros e filtrar na aplicação.
- **Modelagem exige planejamento:** índices e relações entre estruturas precisam ser mantidos pelo código. Neste projeto, o Hash e o Sorted Set precisam permanecer consistentes.
- **Persistência não é igual à de um banco relacional:** AOF oferece recuperação a partir de operações registradas, mas a configuração de persistência, política de gravação e backups precisa ser avaliada conforme a necessidade.
- **Não é a melhor escolha para todo cenário:** aplicações com relacionamentos complexos, consultas analíticas ou necessidade intensa de filtros variados podem se beneficiar mais de outro tipo de banco.

## Estrutura do repositório

```text
.
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── nginx.local.conf
│   ├── package.json
│   └── src/
│       ├── api.ts
│       ├── App.tsx
│       └── ...
├── compose.yaml
└── README.md
```

## Possíveis melhorias futuras

- Criar um índice adicional para filtrar itens por `done` sem percorrer todos os registros.
- Implementar testes automatizados para os endpoints e para as operações Redis.
- Definir limites de memória e política de eviction conforme o cenário de uso.
- Configurar estratégia de backup e testar recuperação dos dados.
- Adicionar autenticação e autorização caso a aplicação seja exposta a usuários reais.
- Avaliar o comportamento de balanceamento e a distribuição de requisições em um ambiente com múltiplas réplicas.

## Conclusão

O projeto demonstra uma implementação prática de Redis como banco NoSQL, utilizando Hash para armazenar os dados dos itens e Sorted Set como índice ordenado por data. A API FastAPI encapsula as operações de leitura e escrita, enquanto o frontend React permite interagir com os registros.

A implementação também explora recursos importantes do Redis, como pipelines transacionais, scripts Lua, consultas ordenadas e persistência AOF. O projeto evidencia tanto os benefícios do Redis quanto algumas limitações de modelagem e consulta que precisam ser consideradas na escolha de um banco de dados.
