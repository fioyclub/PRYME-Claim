import logging
import gc
from typing import Dict, List, Any, Optional, Tuple, Union, cast

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ContextTypes, ConversationHandler, CommandHandler,
                          CallbackQueryHandler)

from config import Config
from sheets_client import SheetsClient
from drive_client import DriveClient
from lazy_client_manager import LazyClientManager
from keyboards import KeyboardBuilder

logger = logging.getLogger(__name__)

# 定义状态
SELECT_ROLE, SELECT_USER, SHOW_STATS, CONFIRM_DELETE = range(4)

# 定义回调数据前缀
ROLE_PREFIX = "total_role:"
USER_PREFIX = "total_user:"
CONFIRM_PREFIX = "total_confirm:"
DELETED_ROLE_PREFIX = "deleted_role:"
DELETED_USER_PREFIX = "deleted_user:"

class AdminCommands:
    """处理管理员命令的类"""
    
    def __init__(self, client_manager: LazyClientManager):
        self.client_manager = client_manager
        self.config = Config()
    
    async def _get_sheets_client(self) -> SheetsClient:
        """获取SheetsClient实例"""
        return await self.client_manager.get_sheets_client()
    
    async def _get_drive_client(self) -> DriveClient:
        """获取DriveClient实例"""
        return await self.client_manager.get_drive_client()
    
    async def _check_admin(self, update: Update) -> bool:
        """检查用户是否为管理员"""
        user_id = update.effective_user.id
        return user_id in self.config.ADMIN_IDS
    
    async def total_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """处理/Total命令"""
        # 检查是否为管理员
        if not await self._check_admin(update):
            await update.message.reply_text("您没有权限使用此命令。")
            return ConversationHandler.END
        
        # 显示角色选择键盘
        keyboard = KeyboardBuilder.build_role_selection_keyboard(
            callback_prefix=ROLE_PREFIX,
            include_cancel=True
        )
        
        await update.message.reply_text(
            "请选择要查看的用户角色：",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return SELECT_ROLE
    
    async def select_role_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """处理角色选择回调"""
        query = update.callback_query
        await query.answer()
        
        # 获取选择的角色
        callback_data = query.data
        if callback_data == "cancel":
            await query.edit_message_text("操作已取消。")
            return ConversationHandler.END
        
        role = callback_data.replace(ROLE_PREFIX, "")
        context.user_data["selected_role"] = role
        
        # 获取该角色下的所有用户
        try:
            sheets_client = await self._get_sheets_client()
            users = await sheets_client.get_all_users_in_role(role)
            
            if not users:
                await query.edit_message_text(f"在 {role} 角色下没有找到用户。")
                return ConversationHandler.END
            
            # 保存用户列表到上下文
            context.user_data["users"] = users
            
            # 创建用户选择键盘
            keyboard = []
            for user in users:
                user_id = user.get("id", "")
                user_name = user.get("name", "未知用户")
                callback_data = f"{USER_PREFIX}{user_id}:{user_name}"
                keyboard.append([InlineKeyboardButton(user_name, callback_data=callback_data)])
            
            # 添加取消按钮
            keyboard.append([InlineKeyboardButton("取消", callback_data="cancel")])
            
            await query.edit_message_text(
                f"请选择要查看的{role}用户：",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return SELECT_USER
            
        except Exception as e:
            logger.error(f"获取用户列表时出错: {e}")
            await query.edit_message_text(f"获取用户列表时出错: {e}")
            return ConversationHandler.END
    
    async def select_user_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """处理用户选择回调"""
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        if callback_data == "cancel":
            await query.edit_message_text("操作已取消。")
            return ConversationHandler.END
        
        # 解析用户ID和名称
        user_data = callback_data.replace(USER_PREFIX, "").split(":")
        if len(user_data) >= 2:
            user_id = user_data[0]
            user_name = user_data[1]
            
            context.user_data["selected_user_id"] = user_id
            context.user_data["selected_user_name"] = user_name
            
            # 获取用户的所有报销记录
            try:
                sheets_client = await self._get_sheets_client()
                claims = await sheets_client.get_user_claims(int(user_id), user_name)
                
                # 计算统计数据
                total_claims = len(claims)
                total_amount = sum(float(claim.get("amount", 0)) for claim in claims)
                categories = set(claim.get("category", "") for claim in claims if claim.get("category"))
                
                # 保存统计数据到上下文
                context.user_data["claims"] = claims
                context.user_data["stats"] = {
                    "total_claims": total_claims,
                    "total_amount": total_amount,
                    "categories": list(categories)
                }
                
                # 显示统计数据
                stats_text = f"用户: {user_name}\n"
                stats_text += f"报销记录总数: {total_claims}\n"
                stats_text += f"累计报销金额: {total_amount:.2f}\n"
                stats_text += f"报销类别: {', '.join(categories) if categories else '无'}\n\n"
                stats_text += "是否删除此用户的所有报销数据和照片？"
                
                # 创建确认键盘
                keyboard = [
                    [InlineKeyboardButton("是", callback_data=f"{CONFIRM_PREFIX}yes")],
                    [InlineKeyboardButton("否", callback_data=f"{CONFIRM_PREFIX}no")]
                ]
                
                await query.edit_message_text(
                    stats_text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                return CONFIRM_DELETE
                
            except Exception as e:
                logger.error(f"获取用户报销记录时出错: {e}")
                await query.edit_message_text(f"获取用户报销记录时出错: {e}")
                return ConversationHandler.END
        else:
            await query.edit_message_text("无效的用户数据。")
            return ConversationHandler.END
    
    async def confirm_delete_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """处理确认删除回调"""
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        confirm = callback_data.replace(CONFIRM_PREFIX, "")
        
        if confirm == "no":
            await query.edit_message_text("操作已取消，数据未删除。")
            
            # 清理上下文数据
            if "selected_role" in context.user_data:
                del context.user_data["selected_role"]
            if "selected_user_id" in context.user_data:
                del context.user_data["selected_user_id"]
            if "selected_user_name" in context.user_data:
                del context.user_data["selected_user_name"]
            if "claims" in context.user_data:
                del context.user_data["claims"]
            if "stats" in context.user_data:
                del context.user_data["stats"]
            if "users" in context.user_data:
                del context.user_data["users"]
            
            gc.collect()
            return ConversationHandler.END
        
        # 执行删除操作
        role = context.user_data.get("selected_role")
        user_id = context.user_data.get("selected_user_id")
        user_name = context.user_data.get("selected_user_name")
        
        if not all([role, user_id, user_name]):
            await query.edit_message_text("缺少必要的用户数据，无法执行删除操作。")
            return ConversationHandler.END
        
        try:
            # 1. 删除Google Drive上的照片
            drive_client = await self._get_drive_client()
            file_result = await drive_client.delete_user_files(int(user_id))
            
            # 2. 删除Google Sheet中的数据
            sheets_client = await self._get_sheets_client()
            sheet_result = await sheets_client.delete_user_data(int(user_id), role, user_name)
            
            # 显示结果
            result_text = f"用户 {user_name} 的数据删除结果:\n\n"
            result_text += f"删除的报销记录: {sheet_result.get('claims_deleted', 0)}\n"
            result_text += f"删除的文件: {file_result.get('deleted_count', 0)}\n"
            
            # 显示任何错误
            sheet_errors = sheet_result.get("errors", [])
            file_errors = file_result.get("errors", [])
            
            if sheet_errors or file_errors:
                result_text += "\n执行过程中出现以下错误:\n"
                for error in sheet_errors:
                    result_text += f"- {error}\n"
                for error in file_errors:
                    result_text += f"- {error}\n"
            
            await query.edit_message_text(result_text)
            
        except Exception as e:
            logger.error(f"删除用户数据时出错: {e}")
            await query.edit_message_text(f"删除用户数据时出错: {e}")
        
        # 清理上下文数据
        if "selected_role" in context.user_data:
            del context.user_data["selected_role"]
        if "selected_user_id" in context.user_data:
            del context.user_data["selected_user_id"]
        if "selected_user_name" in context.user_data:
            del context.user_data["selected_user_name"]
        if "claims" in context.user_data:
            del context.user_data["claims"]
        if "stats" in context.user_data:
            del context.user_data["stats"]
        if "users" in context.user_data:
            del context.user_data["users"]
        
        gc.collect()
        return ConversationHandler.END
    
    async def deleted_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """处理/Deleted命令"""
        # 检查是否为管理员
        if not await self._check_admin(update):
            await update.message.reply_text("您没有权限使用此命令。")
            return ConversationHandler.END
        
        # 显示角色选择键盘
        keyboard = KeyboardBuilder.build_role_selection_keyboard(
            callback_prefix=DELETED_ROLE_PREFIX,
            include_cancel=True
        )
        
        await update.message.reply_text(
            "请选择要删除的用户角色：",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return SELECT_ROLE
    
    async def deleted_select_role_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """处理/Deleted命令的角色选择回调"""
        query = update.callback_query
        await query.answer()
        
        # 获取选择的角色
        callback_data = query.data
        if callback_data == "cancel":
            await query.edit_message_text("操作已取消。")
            return ConversationHandler.END
        
        role = callback_data.replace(DELETED_ROLE_PREFIX, "")
        context.user_data["selected_role"] = role
        
        # 获取该角色下的所有用户
        try:
            sheets_client = await self._get_sheets_client()
            users = await sheets_client.get_all_users_in_role(role)
            
            if not users:
                await query.edit_message_text(f"在 {role} 角色下没有找到用户。")
                return ConversationHandler.END
            
            # 保存用户列表到上下文
            context.user_data["users"] = users
            
            # 创建用户选择键盘
            keyboard = []
            for user in users:
                user_id = user.get("id", "")
                user_name = user.get("name", "未知用户")
                callback_data = f"{DELETED_USER_PREFIX}{user_id}:{user_name}"
                keyboard.append([InlineKeyboardButton(user_name, callback_data=callback_data)])
            
            # 添加取消按钮
            keyboard.append([InlineKeyboardButton("取消", callback_data="cancel")])
            
            await query.edit_message_text(
                f"请选择要删除的{role}用户：",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return SELECT_USER
            
        except Exception as e:
            logger.error(f"获取用户列表时出错: {e}")
            await query.edit_message_text(f"获取用户列表时出错: {e}")
            return ConversationHandler.END
    
    async def deleted_select_user_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """处理/Deleted命令的用户选择回调"""
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        if callback_data == "cancel":
            await query.edit_message_text("操作已取消。")
            return ConversationHandler.END
        
        # 解析用户ID和名称
        user_data = callback_data.replace(DELETED_USER_PREFIX, "").split(":")
        if len(user_data) >= 2:
            user_id = user_data[0]
            user_name = user_data[1]
            
            # 直接执行删除操作
            role = context.user_data.get("selected_role")
            
            if not role:
                await query.edit_message_text("缺少角色信息，无法执行删除操作。")
                return ConversationHandler.END
            
            try:
                await query.edit_message_text(f"正在删除用户 {user_name} 的所有数据，请稍候...")
                
                # 1. 删除Google Drive上的照片
                drive_client = await self._get_drive_client()
                file_result = await drive_client.delete_user_files(int(user_id))
                
                # 2. 删除Google Sheet中的数据
                sheets_client = await self._get_sheets_client()
                sheet_result = await sheets_client.delete_user_data(int(user_id), role, user_name)
                
                # 显示结果
                result_text = f"用户 {user_name} 的数据与文件已清除 ✅\n\n"
                result_text += f"删除的报销记录: {sheet_result.get('claims_deleted', 0)}\n"
                result_text += f"删除的文件: {file_result.get('deleted_count', 0)}\n"
                
                # 显示任何错误
                sheet_errors = sheet_result.get("errors", [])
                file_errors = file_result.get("errors", [])
                
                if sheet_errors or file_errors:
                    result_text += "\n执行过程中出现以下错误:\n"
                    for error in sheet_errors:
                        result_text += f"- {error}\n"
                    for error in file_errors:
                        result_text += f"- {error}\n"
                
                await query.edit_message_text(result_text)
                
            except Exception as e:
                logger.error(f"删除用户数据时出错: {e}")
                await query.edit_message_text(f"删除用户数据时出错: {e}")
            
            # 清理上下文数据
            if "selected_role" in context.user_data:
                del context.user_data["selected_role"]
            if "users" in context.user_data:
                del context.user_data["users"]
            
            gc.collect()
            return ConversationHandler.END
        else:
            await query.edit_message_text("无效的用户数据。")
            return ConversationHandler.END

# 创建ConversationHandler
def get_total_handler(client_manager: LazyClientManager) -> ConversationHandler:
    """获取/Total命令的ConversationHandler"""
    admin_commands = AdminCommands(client_manager)
    
    return ConversationHandler(
        entry_points=[CommandHandler("Total", admin_commands.total_command)],
        states={
            SELECT_ROLE: [
                CallbackQueryHandler(admin_commands.select_role_callback, pattern=f"^{ROLE_PREFIX}"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cancel$")
            ],
            SELECT_USER: [
                CallbackQueryHandler(admin_commands.select_user_callback, pattern=f"^{USER_PREFIX}"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cancel$")
            ],
            CONFIRM_DELETE: [
                CallbackQueryHandler(admin_commands.confirm_delete_callback, pattern=f"^{CONFIRM_PREFIX}")
            ]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=True,
        per_chat=True
    )

def get_deleted_handler(client_manager: LazyClientManager) -> ConversationHandler:
    """获取/Deleted命令的ConversationHandler"""
    admin_commands = AdminCommands(client_manager)
    
    return ConversationHandler(
        entry_points=[CommandHandler("Deleted", admin_commands.deleted_command)],
        states={
            SELECT_ROLE: [
                CallbackQueryHandler(admin_commands.deleted_select_role_callback, pattern=f"^{DELETED_ROLE_PREFIX}"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cancel$")
            ],
            SELECT_USER: [
                CallbackQueryHandler(admin_commands.deleted_select_user_callback, pattern=f"^{DELETED_USER_PREFIX}"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cancel$")
            ]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=True,
        per_chat=True
    )