#!/usr/bin/env python3
"""
Скрипт инкрементальной индексации для Biotact
Индексирует только новые и измененные файлы, экономит время и деньги на API
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, Settings, Document
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.node_parser import SentenceSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, Filter, FieldCondition, MatchValue

# Файл для хранения состояния индексации
INDEX_STATE_FILE = Path("/opt/biotact-core-v2/data/.index_state.json")
DOCS_PATH = Path("/opt/biotact-core-v2/data/knowledge/documents")
COLLECTION_NAME = "biotact_knowledge_v3"


def calculate_file_hash(file_path: Path) -> str:
    """Вычисляет MD5 hash содержимого файла"""
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            md5.update(chunk)
    return md5.hexdigest()


def load_index_state() -> Dict[str, Dict]:
    """Загружает состояние индексации из файла"""
    if INDEX_STATE_FILE.exists():
        with open(INDEX_STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_index_state(state: Dict[str, Dict]):
    """Сохраняет состояние индексации в файл"""
    INDEX_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_current_files() -> Dict[str, Dict]:
    """Получает список текущих файлов с их hash"""
    current_files = {}

    for file_path in DOCS_PATH.glob('*'):
        if file_path.is_file() and file_path.suffix in ['.txt', '.md']:
            file_hash = calculate_file_hash(file_path)
            current_files[str(file_path.name)] = {
                'hash': file_hash,
                'path': str(file_path),
                'size': file_path.stat().st_size,
                'modified': file_path.stat().st_mtime
            }

    return current_files


def initialize_qdrant_client():
    """Инициализирует Qdrant клиент и создает коллекцию если нужно"""
    client = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )

    # Проверяем существование коллекции
    collections = client.get_collections().collections
    collection_exists = any(c.name == COLLECTION_NAME for c in collections)

    if not collection_exists:
        print(f"📦 Создаем новую коллекцию '{COLLECTION_NAME}'...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
        )
        print("✅ Коллекция создана")
    else:
        print(f"✅ Коллекция '{COLLECTION_NAME}' уже существует")

    return client


def delete_document_vectors(client: QdrantClient, filename: str):
    """Удаляет все векторы для указанного файла"""
    try:
        # Ищем все точки с этим filename в метаданных
        scroll_result = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="file_name",
                        match=MatchValue(value=filename)
                    )
                ]
            ),
            limit=1000,
        )

        if scroll_result[0]:
            point_ids = [point.id for point in scroll_result[0]]
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=point_ids
            )
            print(f"  🗑️  Удалено {len(point_ids)} векторов для '{filename}'")
            return len(point_ids)

    except Exception as e:
        print(f"  ⚠️  Ошибка при удалении векторов для '{filename}': {e}")

    return 0


def index_document(client: QdrantClient, file_path: Path, embed_model):
    """Индексирует один документ"""
    print(f"  📄 Индексирую '{file_path.name}'...")

    # Читаем документ
    reader = SimpleDirectoryReader(
        input_files=[str(file_path)],
        filename_as_id=True
    )
    documents = reader.load_data()

    if not documents:
        print(f"  ⚠️  Не удалось прочитать файл")
        return 0

    # Vector store
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
    )

    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Настройки чанков
    Settings.chunk_size = 1024
    Settings.chunk_overlap = 200
    Settings.embed_model = embed_model

    text_splitter = SentenceSplitter(
        chunk_size=1024,
        chunk_overlap=200,
    )

    # Индексируем
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        transformations=[text_splitter],
        show_progress=False,
    )

    # Подсчитываем созданные векторы
    info = client.get_collection(COLLECTION_NAME)
    return info.points_count


def main():
    print("🚀 Инкрементальная индексация Biotact Knowledge Base")
    print("=" * 60)

    # 1. Инициализация
    print("\n📋 Шаг 1: Инициализация...")

    embed_model = OpenAIEmbedding(
        model="text-embedding-3-large",
        api_key=os.getenv("OPENAI_API_KEY"),
        dimensions=3072
    )

    client = initialize_qdrant_client()

    # 2. Загружаем предыдущее состояние
    print("\n📋 Шаг 2: Анализ изменений...")
    old_state = load_index_state()
    current_files = get_current_files()

    # 3. Определяем изменения
    old_filenames = set(old_state.keys())
    current_filenames = set(current_files.keys())

    new_files = current_filenames - old_filenames
    deleted_files = old_filenames - current_filenames
    potentially_modified = current_filenames & old_filenames

    # Проверяем измененные файлы по hash
    modified_files = set()
    for filename in potentially_modified:
        if current_files[filename]['hash'] != old_state[filename]['hash']:
            modified_files.add(filename)

    unchanged_files = potentially_modified - modified_files

    # 4. Выводим статистику
    print(f"\n📊 Статистика изменений:")
    print(f"  ✅ Без изменений: {len(unchanged_files)}")
    print(f"  🆕 Новые файлы: {len(new_files)}")
    print(f"  📝 Изменены: {len(modified_files)}")
    print(f"  🗑️  Удалены: {len(deleted_files)}")

    if not new_files and not modified_files and not deleted_files:
        print("\n✨ Нет изменений, индексация не требуется!")
        return

    # 5. Обработка удаленных файлов
    if deleted_files:
        print(f"\n🗑️  Удаление векторов для {len(deleted_files)} файлов...")
        for filename in deleted_files:
            delete_document_vectors(client, filename)

    # 6. Обработка измененных файлов (удалить старые векторы)
    if modified_files:
        print(f"\n📝 Обновление {len(modified_files)} измененных файлов...")
        for filename in modified_files:
            delete_document_vectors(client, filename)

    # 7. Индексация новых и измененных файлов
    files_to_index = new_files | modified_files

    if files_to_index:
        print(f"\n🔄 Индексация {len(files_to_index)} файлов...")

        initial_count = client.get_collection(COLLECTION_NAME).points_count

        for filename in files_to_index:
            file_path = Path(current_files[filename]['path'])
            status = "🆕 НОВЫЙ" if filename in new_files else "📝 ИЗМЕНЕН"
            print(f"\n{status}: {filename}")

            try:
                index_document(client, file_path, embed_model)
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                continue

        final_count = client.get_collection(COLLECTION_NAME).points_count
        added_vectors = final_count - initial_count
        print(f"\n✅ Добавлено {added_vectors} новых векторов")

    # 8. Сохраняем новое состояние
    print("\n💾 Сохранение состояния...")
    new_state = {}
    for filename in current_filenames:
        new_state[filename] = current_files[filename].copy()
        new_state[filename]['indexed_at'] = datetime.now().isoformat()

    save_index_state(new_state)

    # 9. Финальная статистика
    print("\n" + "=" * 60)
    print("✅ ИНДЕКСАЦИЯ ЗАВЕРШЕНА")
    print("=" * 60)

    info = client.get_collection(COLLECTION_NAME)
    print(f"\n📊 Итоговая статистика коллекции:")
    print(f"  - Всего файлов: {len(current_filenames)}")
    print(f"  - Всего векторов: {info.points_count}")
    print(f"  - Статус коллекции: {info.status}")
    print(f"  - Размер векторов: {info.config.params.vectors.size}")

    print("\n💡 Совет: Теперь при добавлении новых файлов в")
    print(f"   {DOCS_PATH}")
    print("   просто запусти этот скрипт снова - он автоматически")
    print("   проиндексирует только новые и измененные файлы!")


if __name__ == "__main__":
    main()
