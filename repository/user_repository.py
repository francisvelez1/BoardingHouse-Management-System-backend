from models import user



#Read - Find one
async def find_by_username(username: str):
    return await user.find_one(user.username == username)
#Find by email
async def find_by_email(email: str):
    return await user.find_one(user.email == email)
#READ - Find all
async def find_all():
    return await user.find_all().to_list()
# CREATE / UPDATE — save
async def save_user(user: user):
    await user.save()
    return user
#Existing name
async def exists_by_username(username: str) -> bool:
    return await user.find_one(user.username == username) is not None

#existing email
async def exists_by_email(email: str) -> bool:
    return await user.find_one(user.email == email) is not None

# DELETE
async def delete_user(user: user):
    await user.delete()
