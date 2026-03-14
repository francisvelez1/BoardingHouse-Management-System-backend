from models import User



#Read - Find one
async def find_by_username(username: str):
    return await User.find_one(User.username == username)
#Find by email
async def find_by_email(email: str):
    return await User.find_one(User.email == email)
#READ - Find all
async def find_all():
    return await User.find_all().to_list()
# CREATE / UPDATE — save
async def save_user(user: User):
    await user.save()
    return user
#Existing name
async def exists_by_username(username: str) -> bool:
    return await User.find_one(User.username == username) is not None

#existing email
async def exists_by_email(email: str) -> bool:
    return await User.find_one(User.email == email) is not None

# DELETE
async def delete_user(User: User):
    await User.delete()
