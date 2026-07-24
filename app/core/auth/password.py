import bcrypt


class PasswordHandler:
    def hash(self, plain: str) -> str:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    def verify(self, plain: str, hashed: str) -> bool:
        if not hashed:
            return False
        return bcrypt.checkpw(plain.encode(), hashed.encode())
