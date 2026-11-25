from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, HTMLResponse
import markdown2
from invoke_types import InvocationRequest, InvocationResponse
from db import pool
from scripts_api import router as scripts_router
from simple_db_api import router as simple_db_router
from spoiler_story_api import router as spoiler_story_router
from evidence_api import router as evidence_router
from database_api import router as database_router
import json
import os
import base64
import re
from settings import MODEL, MODEL_KEY
from llm_service import respond_initial, critique, refine, check_whether_to_refine, respond_initial_stream
from avatar_generator import generate_avatar_for_character
from cover_generator import generate_cover_for_script
from background_generator import generate_background_for_character
from datetime import datetime, timezone
import time
from pydantic import BaseModel
from typing import Optional

app = FastAPI()
from npc_api import router as npc_router
app.include_router(npc_router)

origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

# 配置静态文件服务
web_dir = os.path.join(os.path.dirname(__file__), '..', 'web')
public_dir = os.path.join(web_dir, 'public')

# 确保所有静态文件目录存在
static_dirs = ['character_avatars', 'script_covers', 'script_scenes', 'evidence_images']
for dir_name in static_dirs:
    dir_path = os.path.join(public_dir, dir_name)
    os.makedirs(dir_path, exist_ok=True)
    print(f"📁 静态文件目录: {dir_path}")

# 挂载静态文件服务
app.mount("/character_avatars", StaticFiles(directory=os.path.join(public_dir, "character_avatars")), name="character_avatars")
app.mount("/script_covers", StaticFiles(directory=os.path.join(public_dir, "script_covers")), name="script_covers")
app.mount("/script_scenes", StaticFiles(directory=os.path.join(public_dir, "script_scenes")), name="script_scenes")
app.mount("/evidence_images", StaticFiles(directory=os.path.join(public_dir, "evidence_images")), name="evidence_images")

# 文档通过动态路由渲染，不需要静态文件挂载

print("🌐 静态文件服务已配置:")
print(f"  - /character_avatars -> {os.path.join(public_dir, 'character_avatars')}")
print(f"  - /script_covers -> {os.path.join(public_dir, 'script_covers')}")
print(f"  - /script_scenes -> {os.path.join(public_dir, 'script_scenes')}")
print(f"  - /evidence_images -> {os.path.join(public_dir, 'evidence_images')}")
print("📚 文档渲染服务:")
print("  - /docs-list -> 文档列表页面")
print("  - /docs/{filename}.md -> 渲染后的文档页面")

# 注册剧本管理API路由
app.include_router(scripts_router, tags=["scripts"])
app.include_router(simple_db_router, tags=["simple_database"])
app.include_router(spoiler_story_router, tags=["spoiler_stories"])
app.include_router(evidence_router, tags=["evidence"])
app.include_router(database_router, tags=["database"])

# 头像生成请求模型
class AvatarGenerationRequest(BaseModel):
    character_name: str
    character_bio: str
    character_personality: Optional[str] = None  # 可选字段，不再用于图像生成

class CoverGenerationRequest(BaseModel):
    script_title: str
    script_description: str

class CoverUploadRequest(BaseModel):
    script_id: str
    base64_image: str
    filename: str

class BackgroundGenerationRequest(BaseModel):
    character_name: str
    character_bio: str
    character_personality: str
    character_context: str = ""

@app.post("/generate_avatar")
async def generate_avatar(request: AvatarGenerationRequest):
    """
    为角色生成电影写真风格的头像
    """
    try:
        print(f'🎭 收到头像生成请求: {request.character_name}')
        
        # 调用头像生成器（只使用名称和背景，不使用性格）
        base64_image = generate_avatar_for_character(
            request.character_name,
            request.character_bio
        )
        
        if base64_image:
            # 确保头像目录存在（使用与静态文件服务相同的路径配置）
            web_dir = os.path.join(os.path.dirname(__file__), '..', 'web')
            public_dir = os.path.join(web_dir, 'public')
            avatar_dir = os.path.join(public_dir, 'character_avatars')
            os.makedirs(avatar_dir, exist_ok=True)
            
            # 保存头像文件
            avatar_filename = f"{request.character_name}.png"
            avatar_path = os.path.join(avatar_dir, avatar_filename)
            
            # 解码base64并保存
            image_data = base64.b64decode(base64_image)
            with open(avatar_path, 'wb') as f:
                f.write(image_data)
            
            print(f'✅ 头像已保存: {avatar_path}')
            
            return {
                "success": True,
                "message": f"头像生成成功",
                "avatar_filename": avatar_filename,
                "avatar_path": f"character_avatars/{avatar_filename}",
                "base64_image": base64_image
            }
        else:
            return {
                "success": False,
                "message": "头像生成失败，请重试",
                "avatar_filename": None,
                "avatar_path": None,
                "base64_image": None
            }
            
    except Exception as e:
        print(f'❌ 头像生成异常: {str(e)}')
        raise HTTPException(status_code=500, detail=f"头像生成失败: {str(e)}")

@app.post("/generate_cover")
async def generate_cover(request: CoverGenerationRequest):
    """
    为剧本生成电影写真风格的封面
    
    Args:
        request: 包含剧本标题和描述的请求
        
    Returns:
        生成的封面图片base64数据
    """
    try:
        print(f'🎬 开始为剧本生成封面: {request.script_title}')
        
        # 调用封面生成器
        base64_image = generate_cover_for_script(
            request.script_title, 
            request.script_description
        )
        
        if base64_image:
            # 生成唯一文件名
            timestamp = int(time.time() * 1000)
            cover_filename = f"script_cover_{timestamp}.png"
            
            # 保存到两个位置：assets目录和public目录
            cover_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'src', 'assets', 'script_covers')
            public_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'script_covers')
            
            cover_path = os.path.join(cover_dir, cover_filename)
            public_path = os.path.join(public_dir, cover_filename)
            
            # 确保目录存在
            os.makedirs(cover_dir, exist_ok=True)
            os.makedirs(public_dir, exist_ok=True)
            
            # 解码base64并保存到两个位置
            image_data = base64.b64decode(base64_image)
            with open(cover_path, 'wb') as f:
                f.write(image_data)
            with open(public_path, 'wb') as f:
                f.write(image_data)
            
            print(f'✅ 封面已保存: {cover_path} 和 {public_path}')
            
            return {
                "success": True,
                "message": f"封面生成成功",
                "cover_filename": cover_filename,
                "cover_path": f"script_covers/{cover_filename}",
                "base64_image": base64_image
            }
        else:
            return {
                "success": False,
                "message": "封面生成失败，请重试",
                "cover_filename": None,
                "cover_path": None,
                "base64_image": None
            }
            
    except Exception as e:
        print(f'❌ 封面生成异常: {str(e)}')
        raise HTTPException(status_code=500, detail=f"封面生成失败: {str(e)}")

@app.post("/generate_background")
async def generate_background(request: BackgroundGenerationRequest):
    """
    为角色生成聊天背景图片
    """
    try:
        print(f'🎭 收到背景生成请求: {request.character_name}')
        
        # 创建Actor对象
        from invoke_types import Actor
        actor = Actor(
            id=0,  # 临时ID
            name=request.character_name,
            bio=request.character_bio,
            personality=request.character_personality,
            context=request.character_context,
            messages=[],
            secret="",
            violation=""
        )
        
        # 生成背景图片
        result = generate_background_for_character(actor)
        
        if result:
            # 检查返回的是路径还是base64数据
            if result.startswith('script_scenes/'):
                # 预设背景路径
                return {
                    "success": True,
                    "message": "使用预设背景",
                    "background_filename": result.split('/')[-1],
                    "background_path": result,
                    "base64_image": None
                }
            else:
                # AI生成的base64图片数据
                base64_image = result
                
                # 保存背景图片到script_scenes目录
                timestamp = int(time.time() * 1000)
                background_filename = f"chat_bg_{request.character_name}_{timestamp}.png"
                
                # 保存到script_scenes目录
                scenes_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'script_scenes')
                
                # 确保目录存在
                os.makedirs(scenes_dir, exist_ok=True)
                
                # 保存背景图片
                background_path = os.path.join(scenes_dir, background_filename)
                
                with open(background_path, 'wb') as f:
                    f.write(base64.b64decode(base64_image))
                
                print(f'✅ 背景已保存: {background_path}')
                
                return {
                    "success": True,
                    "message": "背景生成成功",
                    "background_filename": background_filename,
                    "background_path": f"script_scenes/{background_filename}",
                    "base64_image": base64_image
                }
        else:
            return {
                "success": False,
                "message": "背景生成失败，请重试",
                "background_filename": None,
                "background_path": None,
                "base64_image": None
            }
            
    except Exception as e:
        print(f'❌ 背景生成异常: {str(e)}')
        raise HTTPException(status_code=500, detail=f"背景生成失败: {str(e)}")

@app.post("/upload_cover")
async def upload_cover(request: CoverUploadRequest):
    """
    上传剧本封面
    
    Args:
        request: 包含剧本ID、base64图片数据和文件名的请求
        
    Returns:
        上传结果和封面文件路径
    """
    try:
        print(f'🖼️ 开始上传剧本封面: {request.script_id}')
        
        # 生成唯一文件名
        timestamp = int(time.time() * 1000)
        file_extension = request.filename.split('.')[-1] if '.' in request.filename else 'png'
        cover_filename = f"script_cover_{request.script_id}_{timestamp}.{file_extension}"
        
        # 保存到两个位置：assets目录和public目录
        cover_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'src', 'assets', 'script_covers')
        public_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'script_covers')
        
        cover_path = os.path.join(cover_dir, cover_filename)
        public_path = os.path.join(public_dir, cover_filename)
        
        # 确保目录存在
        os.makedirs(cover_dir, exist_ok=True)
        os.makedirs(public_dir, exist_ok=True)
        
        # 解码base64并保存到两个位置
        image_data = base64.b64decode(request.base64_image)
        with open(cover_path, 'wb') as f:
            f.write(image_data)
        with open(public_path, 'wb') as f:
            f.write(image_data)
        
        print(f'✅ 封面上传成功: {cover_path} 和 {public_path}')
        
        return {
            "success": True,
            "message": "封面上传成功",
            "cover_filename": cover_filename,
            "cover_path": f"script_covers/{cover_filename}",
            "base64_image": request.base64_image
        }
        
    except Exception as e:
        print(f'❌ 封面上传异常: {str(e)}')
        raise HTTPException(status_code=500, detail=f"封面上传失败: {str(e)}")

@app.get("/list_cover_images")
async def list_cover_images():
    """
    获取系统封面图库列表
    
    @deprecated 此API已废弃，请使用 /script-covers 替代（与证物系统保持一致）
    
    Returns:
        封面图片文件列表
    """
    try:
        # 扫描两个目录：assets目录和public目录
        cover_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'src', 'assets', 'script_covers')
        public_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'script_covers')
        
        # 获取所有图片文件
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
        image_files = []
        
        # 优先从public目录获取（因为这些可以直接访问）
        if os.path.exists(public_dir):
            for filename in os.listdir(public_dir):
                if any(filename.lower().endswith(ext) for ext in image_extensions):
                    file_path = os.path.join(public_dir, filename)
                    file_size = os.path.getsize(file_path)
                    image_files.append({
                        "filename": filename,
                        "path": f"script_covers/{filename}",  # public子目录下的文件路径
                        "size": file_size
                    })
        
        # 如果public目录没有文件，再检查assets目录
        if len(image_files) == 0 and os.path.exists(cover_dir):
            for filename in os.listdir(cover_dir):
                if any(filename.lower().endswith(ext) for ext in image_extensions):
                    file_path = os.path.join(cover_dir, filename)
                    file_size = os.path.getsize(file_path)
                    image_files.append({
                        "filename": filename,
                        "path": f"script_covers/{filename}",
                        "size": file_size
                    })
        
        # 按修改时间排序，最新的在前
        if image_files:
            # 根据实际文件位置来排序
            def get_file_mtime(x):
                public_path = os.path.join(public_dir, x["filename"])
                assets_path = os.path.join(cover_dir, x["filename"])
                if os.path.exists(public_path):
                    return os.path.getmtime(public_path)
                elif os.path.exists(assets_path):
                    return os.path.getmtime(assets_path)
                return 0
            
            image_files.sort(key=get_file_mtime, reverse=True)
        
        print(f'📁 找到 {len(image_files)} 个封面图片文件')
        
        return {
            "success": True,
            "images": image_files
        }
        
    except Exception as e:
        print(f'❌ 获取封面图库异常: {str(e)}')
        raise HTTPException(status_code=500, detail=f"获取封面图库失败: {str(e)}")

@app.get("/get_cover_image/{filename}")
async def get_cover_image(filename: str):
    """
    获取封面图片的base64数据
    
    @deprecated 此API已废弃，请直接使用静态文件路径 /script_covers/{filename} 访问（与证物系统保持一致）
    
    Args:
        filename: 图片文件名
        
    Returns:
        图片的base64数据
    """
    try:
        # 优先从public目录获取
        public_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'script_covers')
        cover_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'src', 'assets', 'script_covers')
        
        public_path = os.path.join(public_dir, filename)
        assets_path = os.path.join(cover_dir, filename)
        
        # 选择存在的文件路径
        if os.path.exists(public_path):
            file_path = public_path
        elif os.path.exists(assets_path):
            file_path = assets_path
        else:
            raise HTTPException(status_code=404, detail="图片文件不存在")
        
        # 读取文件并转换为base64
        with open(file_path, 'rb') as f:
            image_data = f.read()
            base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # 获取文件扩展名以确定MIME类型
        file_extension = filename.split('.')[-1].lower()
        mime_type = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'webp': 'image/webp',
            'bmp': 'image/bmp'
        }.get(file_extension, 'image/png')
        
        print(f'📷 获取封面图片: {filename}')
        
        return {
            "success": True,
            "filename": filename,
            "base64_image": base64_image,
            "mime_type": mime_type,
            "data_url": f"data:{mime_type};base64,{base64_image}"
        }
        
    except Exception as e:
        print(f'❌ 获取封面图片异常: {str(e)}')
        raise HTTPException(status_code=500, detail=f"获取封面图片失败: {str(e)}")

class CoverDeleteRequest(BaseModel):
    filenames: list[str]

@app.delete("/delete_cover_images")
async def delete_cover_images(request: CoverDeleteRequest):
    """
    批量删除封面图片
    
    Args:
        request: 包含要删除的文件名列表的请求
        
    Returns:
        删除结果
    """
    try:
        print(f'🗑️ 开始批量删除封面图片: {len(request.filenames)} 个文件')
        
        # 删除的文件路径
        cover_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'src', 'assets', 'script_covers')
        public_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'script_covers')
        
        deleted_files = []
        failed_files = []
        
        for filename in request.filenames:
            try:
                # 删除assets目录中的文件
                cover_path = os.path.join(cover_dir, filename)
                if os.path.exists(cover_path):
                    os.remove(cover_path)
                    print(f'✅ 已删除assets文件: {filename}')
                
                # 删除public目录中的文件
                public_path = os.path.join(public_dir, filename)
                if os.path.exists(public_path):
                    os.remove(public_path)
                    print(f'✅ 已删除public文件: {filename}')
                
                deleted_files.append(filename)
                
            except Exception as e:
                print(f'❌ 删除文件失败 {filename}: {str(e)}')
                failed_files.append({
                    "filename": filename,
                    "error": str(e)
                })
        
        print(f'🎯 批量删除完成: 成功 {len(deleted_files)} 个，失败 {len(failed_files)} 个')
        
        return {
            "success": True,
            "message": f"批量删除完成: 成功 {len(deleted_files)} 个，失败 {len(failed_files)} 个",
            "deleted_files": deleted_files,
            "failed_files": failed_files
        }
        
    except Exception as e:
        print(f'❌ 批量删除封面图片异常: {str(e)}')
        raise HTTPException(status_code=500, detail=f"批量删除封面图片失败: {str(e)}")

def create_conversation_turn(conn, request: InvocationRequest) -> int:
    if conn is None:
        return 0

    try:
        with conn.cursor() as cur:        
            serialized_chat_messages = [msg.model_dump() for msg in request.actor.messages]
            cur.execute(
                "INSERT INTO conversation_turns (session_id, character_file_version, model, model_key, actor_name, chat_messages) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (request.session_id, request.character_file_version,
                 MODEL, MODEL_KEY, request.actor.name, json.dumps(serialized_chat_messages), )
            )
            turn_id = cur.fetchone()[0]
        conn.commit()
        return turn_id
    except Exception as e:
        conn.rollback()
        print(f"Error in create_conversation_turn: {e}")
        return 0

def store_response(conn, turn_id: int, response: InvocationResponse):
    try:
        with conn.cursor() as cur:
            cur.execute(
               "UPDATE conversation_turns SET original_response = %s, critique_response = %s, problems_detected = %s, "
               "final_response = %s, refined_response = %s, finished_at= %s WHERE id=%s",
                  (response.original_response, response.critique_response, response.problems_detected, response.final_response,
                    response.refined_response, datetime.now(tz=timezone.utc).isoformat(), turn_id, )
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error in store_response: {e}")

def prompt_ai(conn, request: InvocationRequest) -> InvocationResponse:
    turn_id = create_conversation_turn(conn, request)
    print(f"Serving turn {turn_id}")

    # UNREFINED
    unrefined_response = respond_initial(conn, turn_id, request)

    print(f"\nunrefined_response: {unrefined_response}\n")

    critique_response = critique(conn, turn_id, request, unrefined_response)

    print(f"\ncritique_response: {critique_response}\n")

    problems_found = check_whether_to_refine(critique_response)

    if problems_found:
        refined_response = refine(conn, turn_id, request, critique_response, unrefined_response)
        
        final_response = refined_response
    else:
        final_response = unrefined_response
        refined_response = None

    response = InvocationResponse(
        original_response=unrefined_response,
        critique_response=critique_response,
        problems_detected=problems_found,
        final_response=final_response,
        refined_response=refined_response,
    )

    if conn is not None:
        store_start = time.time()
        store_response(conn, turn_id, response)
        print(f"Stored in {time.time() - store_start:.2f}s")

    return response

@app.post("/invoke")
async def invoke(request: InvocationRequest):
    start_time = time.time()
    connection_pool = pool()
    
    conn = None
    try:
        # Use a mock connection object or None if the pool is not available
        conn = connection_pool.getconn() if connection_pool else None
        
        conn_time = time.time()
        print(f"Conn in {conn_time - start_time:.2f}s")
        response = prompt_ai(conn, request)
        response_time = time.time()
        print(f"Response in {response_time - conn_time:.2f}s")

        return response.model_dump()
    finally:
        if conn:
            connection_pool.putconn(conn)

@app.post("/invoke/stream")
async def invoke_stream(request: InvocationRequest):
    """流式版本的invoke端点"""
    start_time = time.time()
    connection_pool = pool()
    
    conn = None
    try:
        conn = connection_pool.getconn() if connection_pool else None
        
        # 创建对话轮次
        turn_id = create_conversation_turn(conn, request)
        print(f"Serving turn {turn_id} (streaming)")
        
        def generate_response():
            try:
                # 使用流式响应
                for chunk in respond_initial_stream(conn, turn_id, request):
                    # 发送SSE格式的数据
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                
                # 发送结束信号
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
                
            except Exception as e:
                print(f"Error in streaming response: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        return StreamingResponse(
            generate_response(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
            }
        )
    finally:
        if conn:
            connection_pool.putconn(conn)

@app.get("/health")
async def health_check():
    # TODO: Implement a better health check mechanism here
    return {"status": "ok"}

# 证物图像生成和管理API
@app.post("/generate-evidence-image")
async def generate_evidence_image(request: dict):
    """生成证物图像"""
    try:
        from evidence_generator import generate_evidence_image_for_item
        import os
        import base64
        import uuid
        
        name = request.get('name', '')
        description = request.get('description', '')
        style = request.get('style', 'realistic')
        
        if not name or not description:
            return {"success": False, "error": "证物名称和描述不能为空"}
        
        print(f"🔍 开始生成证物图像: {name}")
        
        # 调用新的证物图像生成器
        base64_image = generate_evidence_image_for_item(name, description, style)
        
        if base64_image:
            # 确保证物图像目录存在
            evidence_dir = "../web/public/evidence_images"
            os.makedirs(evidence_dir, exist_ok=True)
            
            # 生成唯一文件名
            timestamp = str(int(time.time() * 1000))
            safe_name = re.sub(r'[^\w\-_]', '_', name)
            filename = f"evidence_{safe_name}_{timestamp}.png"
            filepath = os.path.join(evidence_dir, filename)
            
            # 保存base64图像为文件
            try:
                image_data = base64.b64decode(base64_image)
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                
                print(f"✅ 证物图像保存成功: {filepath}")
                
                return {
                    "success": True,
                    "imageUrl": f"/evidence_images/{filename}",
                    "imagePath": f"evidence_images/{filename}"
                }
            except Exception as save_error:
                print(f"❌ 证物图像保存失败: {str(save_error)}")
                return {"success": False, "error": f"图像保存失败: {str(save_error)}"}
        else:
            print(f"❌ 证物图像生成失败: {name}")
            error_message = "图像生成失败，可能原因：\n1. 内容包含敏感词汇被审核拦截\n2. 描述过于简单或模糊\n3. API服务暂时不可用\n\n建议：请尝试使用更具体、更中性的描述词汇"
            return {"success": False, "error": error_message}
        
    except Exception as e:
        print(f"❌ 证物图像生成异常: {str(e)}")
        return {"success": False, "error": f"服务异常: {str(e)}"}

@app.post("/upload-evidence-image")
async def upload_evidence_image(file: UploadFile = File(...), name: str = Form(...)):
    """上传证物图像"""
    try:
        import uuid
        import os
        from PIL import Image
        import io
        
        # 验证文件类型
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if file.content_type not in allowed_types:
            return {"success": False, "error": "只支持 JPEG、PNG、GIF、WebP 格式的图片"}
        
        # 验证文件大小 (5MB)
        file_content = await file.read()
        if len(file_content) > 5 * 1024 * 1024:
            return {"success": False, "error": "图片大小不能超过 5MB"}
        
        # 确保证物图像目录存在
        evidence_dir = "web/public/evidence_images"
        os.makedirs(evidence_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = str(int(time.time() * 1000))
        safe_name = re.sub(r'[^\w\-_]', '_', name)
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'png'
        filename = f"evidence_{safe_name}_{timestamp}.{file_extension}"
        filepath = os.path.join(evidence_dir, filename)
        
        # 压缩并保存图像
        image = Image.open(io.BytesIO(file_content))
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')
        
        # 调整尺寸
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        image.save(filepath, optimize=True, quality=85)
        
        return {
            "success": True,
            "imageUrl": f"/evidence_images/{filename}",
            "imagePath": f"evidence_images/{filename}"
        }
        
    except Exception as e:
        print(f"证物图像上传失败: {str(e)}")
        return {"success": False, "error": str(e)}

@app.delete("/delete-evidence-image")
async def delete_evidence_image(request: dict):
    """删除证物图像"""
    try:
        import os
        
        image_name = request.get('imageName', '')
        if not image_name:
            return {"success": False, "error": "图像名称不能为空"}
        
        # 安全检查：只删除证物图像目录中的文件
        if not image_name.startswith('evidence_'):
            return {"success": False, "error": "只能删除证物图像"}
        
        filepath = f"web/public/evidence_images/{image_name}"
        if os.path.exists(filepath):
            os.remove(filepath)
            return {"success": True}
        else:
            return {"success": False, "error": "图像文件不存在"}
            
    except Exception as e:
        print(f"删除证物图像失败: {str(e)}")
        return {"success": False, "error": str(e)}

@app.get("/evidence-images")
async def get_evidence_images():
    """获取证物图像列表"""
    try:
        import os
        
        # 使用与静态文件服务相同的路径配置
        web_dir = os.path.join(os.path.dirname(__file__), '..', 'web')
        public_dir = os.path.join(web_dir, 'public')
        evidence_dir = os.path.join(public_dir, 'evidence_images')
        
        if not os.path.exists(evidence_dir):
            print(f"证物图像目录不存在: {evidence_dir}")
            return {"images": []}
        
        images = []
        for filename in os.listdir(evidence_dir):
            if filename.startswith('evidence_') and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                images.append(filename)
        
        print(f"找到 {len(images)} 个证物图像: {images}")
        return {"images": sorted(images)}
        
    except Exception as e:
        print(f"获取证物图像列表失败: {str(e)}")
        return {"images": []}

@app.get("/script-covers")
async def get_script_covers():
    """获取剧本封面图像列表（与证物系统保持一致的API设计）"""
    try:
        import os
        
        # 使用与静态文件服务相同的路径配置
        web_dir = os.path.join(os.path.dirname(__file__), '..', 'web')
        public_dir = os.path.join(web_dir, 'public')
        covers_dir = os.path.join(public_dir, 'script_covers')
        
        if not os.path.exists(covers_dir):
            print(f"剧本封面目录不存在: {covers_dir}")
            return {"images": []}
        
        images = []
        for filename in os.listdir(covers_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
                images.append(filename)
        
        print(f"找到 {len(images)} 个剧本封面图像: {images}")
        return {"images": sorted(images)}
    except Exception as e:
        print(f"获取剧本封面图像列表失败: {e}")
        return {"images": []}

@app.get("/docs/{doc_name}")
async def get_rendered_doc(doc_name: str):
    """
    渲染 Markdown 文档为美观的 HTML 页面
    """
    try:
        # 构建文档路径
        docs_dir = os.path.join(os.path.dirname(__file__), '..', 'docs')
        doc_path = os.path.join(docs_dir, doc_name)
        
        # 确保文件存在且是 .md 文件
        if not os.path.exists(doc_path):
            raise HTTPException(status_code=404, detail=f"文档 {doc_name} 不存在")
        
        if not doc_name.endswith('.md'):
            raise HTTPException(status_code=400, detail="只支持 Markdown 文件")
        
        # 读取 Markdown 文件
        with open(doc_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # 渲染为 HTML
        html_content = markdown2.markdown(
            markdown_content, 
            extras=[
                'fenced-code-blocks',  # 代码块支持
                'tables',              # 表格支持
                'task_list',           # 任务列表支持
                'toc',                 # 目录支持
                'header-ids',          # 标题ID支持
                'code-friendly'        # 代码友好
            ]
        )
        
        # 创建美观的 HTML 页面
        full_html = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{doc_name} - 项目文档</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #fafafa;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                h1, h2, h3, h4, h5, h6 {{
                    color: #2c3e50;
                    margin-top: 2em;
                    margin-bottom: 1em;
                }}
                h1 {{
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 10px;
                }}
                h2 {{
                    border-bottom: 2px solid #ecf0f1;
                    padding-bottom: 8px;
                }}
                code {{
                    background-color: #f8f9fa;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
                    color: #e74c3c;
                }}
                pre {{
                    background-color: #2c3e50;
                    color: #ecf0f1;
                    padding: 20px;
                    border-radius: 8px;
                    overflow-x: auto;
                    margin: 20px 0;
                }}
                pre code {{
                    background: none;
                    color: inherit;
                    padding: 0;
                }}
                blockquote {{
                    border-left: 4px solid #3498db;
                    margin: 20px 0;
                    padding: 10px 20px;
                    background-color: #ecf0f1;
                    font-style: italic;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 20px 0;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 12px;
                    text-align: left;
                }}
                th {{
                    background-color: #3498db;
                    color: white;
                }}
                tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                .toc {{
                    background-color: #ecf0f1;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .emoji {{
                    font-size: 1.2em;
                }}
                a {{
                    color: #3498db;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                .back-link {{
                    display: inline-block;
                    margin-bottom: 20px;
                    padding: 8px 16px;
                    background-color: #3498db;
                    color: white;
                    border-radius: 4px;
                    text-decoration: none;
                }}
                .back-link:hover {{
                    background-color: #2980b9;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <a href="/docs-list" class="back-link">← 返回文档列表</a>
                {html_content}
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=full_html)
        
    except Exception as e:
        print(f"渲染文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"渲染文档失败: {str(e)}")

@app.get("/docs-list")
async def get_docs_list():
    """
    显示所有可用文档的列表
    """
    try:
        docs_dir = os.path.join(os.path.dirname(__file__), '..', 'docs')
        
        if not os.path.exists(docs_dir):
            return HTMLResponse(content="<h1>文档目录不存在</h1>")
        
        # 获取所有 .md 文件
        md_files = []
        for filename in os.listdir(docs_dir):
            if filename.endswith('.md'):
                # 读取文件第一行作为标题
                file_path = os.path.join(docs_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                        # 移除 markdown 标题标记
                        title = first_line.lstrip('# ').strip()
                        if not title:
                            title = filename
                except:
                    title = filename
                
                md_files.append({
                    'filename': filename,
                    'title': title
                })
        
        # 按文件名排序
        md_files.sort(key=lambda x: x['filename'])
        
        # 生成文档列表 HTML
        docs_html = """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>项目文档中心</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #fafafa;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #2c3e50;
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 10px;
                    text-align: center;
                }}
                .doc-list {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                    gap: 20px;
                    margin-top: 30px;
                }}
                .doc-item {{
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    padding: 20px;
                    background-color: #fafafa;
                    transition: all 0.3s ease;
                }}
                .doc-item:hover {{
                    background-color: #ecf0f1;
                    transform: translateY(-2px);
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                }}
                .doc-item a {{
                    color: #2c3e50;
                    text-decoration: none;
                    display: block;
                }}
                .doc-item h3 {{
                    margin: 0 0 10px 0;
                    color: #3498db;
                }}
                .doc-filename {{
                    font-size: 0.9em;
                    color: #7f8c8d;
                    font-family: monospace;
                }}
                .stats {{
                    text-align: center;
                    margin-top: 30px;
                    padding: 20px;
                    background-color: #ecf0f1;
                    border-radius: 8px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📚 项目文档中心</h1>
                <div class="stats">
                    <strong>共找到 {count} 个文档</strong>
                </div>
                <div class="doc-list">
        """.format(count=len(md_files))
        
        for doc in md_files:
            docs_html += f"""
                    <div class="doc-item">
                        <a href="/docs/{doc['filename']}">
                            <h3>{doc['title']}</h3>
                            <div class="doc-filename">{doc['filename']}</div>
                        </a>
                    </div>
            """
        
        docs_html += """
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=docs_html)
        
    except Exception as e:
        print(f"获取文档列表失败: {str(e)}")
        return HTMLResponse(content=f"<h1>获取文档列表失败: {str(e)}</h1>")

@app.get("/character-avatars")
async def get_character_avatars():
    """获取角色头像列表"""
    try:
        import os
        
        # 使用与静态文件服务相同的路径配置
        web_dir = os.path.join(os.path.dirname(__file__), '..', 'web')
        public_dir = os.path.join(web_dir, 'public')
        avatars_dir = os.path.join(public_dir, 'character_avatars')
        
        if not os.path.exists(avatars_dir):
            print(f"角色头像目录不存在: {avatars_dir}")
            return {"avatars": []}
        
        avatars = []
        for filename in os.listdir(avatars_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                avatars.append(filename)
        
        print(f"找到 {len(avatars)} 个角色头像: {avatars[:5]}...")  # 只显示前5个，避免日志过长
        return {"avatars": sorted(avatars)}
        
    except Exception as e:
        print(f"获取角色头像列表失败: {str(e)}")
        return {"avatars": []}
