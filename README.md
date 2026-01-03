# 📡 Anime Data Static API

Esta é uma API estática de Animes (Dublados e Legendados) gerada automaticamente e hospedada diretamente no GitHub.  
Os dados podem ser consumidos gratuitamente via CDN (jsDelivr) com alta performance.

---

## 🚀 Base URL

Para consumir os dados, utilize o padrão de URL abaixo:

```
https://cdn.jsdelivr.net/gh/pacdt/anm-db@main/api_dist/v1
```

---

## 📚 Endpoints Disponíveis

### 1. Listar Todos os Animes

Retorna uma lista resumida de todos os animes disponíveis no catálogo.  
Ideal para preencher uma tela de **Pesquisa** ou **Catálogo Completo**.

- **URL:** `/animes/all.json`
- **Exemplo:**
```
https://cdn.jsdelivr.net/gh/pacdt/anm-db@main/api_dist/v1/animes/all.json
```

**Resposta:**
```json
[
  {
    "title": "One Piece",
    "slug": "one-piece",
    "image": "https://cdn.myanimelist.net/images/anime/6/73245l.jpg",
    "score": 8.7,
    "type": "legendado"
  }
]
```

---

### 2. Detalhes do Anime

Retorna todos os metadados, sinopse, gêneros e a lista de episódios (com links de vídeo) de um anime específico.

- **URL:** `/animes/{slug}.json`
- **Exemplo:**
```
https://cdn.jsdelivr.net/gh/pacdt/anm-db@main/api_dist/v1/animes/one-piece.json
```

**Resposta:**
```json
{
  "id": 21,
  "slug": "one-piece",
  "type": "legendado",
  "title": "One Piece",
  "title_english": "One Piece",
  "title_japanese": "ONE PIECE",
  "image": "https://cdn.myanimelist.net/images/anime/6/73245l.jpg",
  "score": 8.7,
  "synopsis": "Gol D. Roger was known as the 'Pirate King'...",
  "trailer_url": "https://www.youtube-nocookie.com/embed/...",
  "genres": ["Action", "Adventure", "Fantasy"],
  "episodes": [
    {
      "numero": 1,
      "url": "https://link-do-video.mp4",
      "nome": "I'm Luffy! The Man Who's Gonna Be King of the Pirates!"
    }
  ]
}
```

---

### 3. Listar Gêneros Disponíveis

Retorna uma lista de todos os gêneros cadastrados e a quantidade de animes em cada um.  
Útil para criar uma sidebar de categorias.

- **URL:** `/genres/list.json`
- **Exemplo:**
```
https://cdn.jsdelivr.net/gh/pacdt/anm-db@main/api_dist/v1/genres/list.json
```

**Resposta:**
```json
[
  {
    "name": "Action",
    "slug": "action",
    "count": 154
  },
  {
    "name": "Comedy",
    "slug": "comedy",
    "count": 89
  }
]
```

---

### 4. Animes por Gênero

Retorna a lista de animes que pertencem a um gênero específico.

- **URL:** `/genres/{slug_do_genero}.json`
- **Exemplo (Ação):**
```
https://cdn.jsdelivr.net/gh/pacdt/anm-db@main/api_dist/v1/genres/action.json
```

**Resposta:**
```json
{
  "name": "Action",
  "slug": "action",
  "count": 154,
  "animes": [
    {
      "title": "Naruto",
      "slug": "naruto",
      "image": "...",
      "score": 7.9,
      "type": "dublado"
    }
  ]
}
```

---

### 5. Novos Animes (Recém Adicionados/Atualizados)

Retorna uma lista dos 20 animes que foram adicionados ou atualizados mais recentemente na base de dados.

- **URL:** `/animes/new_animes.json`
- **Exemplo:**
```
https://cdn.jsdelivr.net/gh/pacdt/anm-db@main/api_dist/v1/animes/new_animes.json
```

**Resposta:**
```json
[
  {
    "title": "Solo Leveling",
    "slug": "solo-leveling",
    "image": "...",
    "score": 8.4,
    "type": "legendado",
    "updated_at": "2023-10-27 15:30:00"
  }
]
```

---

### 6. Últimos Episódios Lançados

Retorna uma lista dos episódios mais recentes detectados pelo sistema (baseado na data de atualização do anime).

- **URL:** `/animes/latest_episodes.json`
- **Exemplo:**
```
https://cdn.jsdelivr.net/gh/pacdt/anm-db@main/api_dist/v1/animes/latest_episodes.json
```

**Resposta:**
```json
[
  {
    "anime_title": "One Piece",
    "anime_slug": "one-piece",
    "anime_image": "...",
    "episode_number": 1080,
    "episode_title": "Episódio 1080",
    "episode_url": "...",
    "type": "legendado",
    "created_at": "2023-10-27 15:30:00"
  }
]
```

---

## 🛠 Como Usar (Exemplo JavaScript)

```javascript
const BASE_URL = "https://cdn.jsdelivr.net/gh/pacdt/anm-db@main/api_dist/v1";

// 1. Pegar todos os animes
async function getAllAnimes() {
  const response = await fetch(`${BASE_URL}/animes/all.json`);
  const data = await response.json();
  console.log(data);
}

// 2. Pegar detalhes de um anime específico
async function getAnimeDetails(slug) {
  const response = await fetch(`${BASE_URL}/animes/${slug}.json`);
  const data = await response.json();
  console.log(data.episodes);
}
```

---

## ⚠️ Notas Importantes

- **Cache:** O jsDelivr possui cache agressivo. Após atualizar o repositório, pode levar alguns minutos para refletir na API.
- **Atualização:** Os dados são atualizados automaticamente a cada 24 horas pelo script do servidor.
