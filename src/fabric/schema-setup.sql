-- Database Schema for DriveThru Agent
-- Run this script in your Fabric SQL Database query editor
--
-- After this script runs, populate richer demo data with the Python seeder:
--   python -m src.fabric.seed_demo_data --dry-run        # preview
--   python -m src.fabric.seed_demo_data --reset --yes    # apply
-- See wiki/database-guide.md for details.

-- ============================================================
-- 1. Menu Table
-- ============================================================
CREATE TABLE Menu (
    MenuItemId VARCHAR(50) PRIMARY KEY,
    ItemName VARCHAR(100) NOT NULL,
    Category VARCHAR(50) NOT NULL,
    Description NVARCHAR(500),
    Price DECIMAL(10, 2) NOT NULL,
    IsAvailable BIT DEFAULT 1,
    Allergens NVARCHAR(200),
    CalorieCount INT,
    ImageUrl VARCHAR(500),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    UpdatedAt DATETIME2 DEFAULT GETUTCDATE()
);

CREATE INDEX IX_Menu_Category ON Menu(Category);
CREATE INDEX IX_Menu_IsAvailable ON Menu(IsAvailable);

-- Insert sample menu items
INSERT INTO Menu (MenuItemId, ItemName, Category, Description, Price, IsAvailable, CalorieCount)
VALUES 
    ('BURGER_001', 'Classic Cheeseburger', 'burgers', 'Our signature cheeseburger with lettuce, tomato, and special sauce', 8.99, 1, 650),
    ('BURGER_002', 'DriveThru Deluxe', 'burgers', 'Double patty with bacon, cheese, and all the fixings', 12.99, 1, 920),
    ('CHICKEN_001', 'Crispy Chicken Sandwich', 'chicken', 'Breaded chicken breast with pickles and mayo', 9.99, 1, 580),
    ('SIDE_001', 'French Fries', 'sides', 'Golden crispy fries', 3.49, 1, 380),
    ('SIDE_002', 'Onion Rings', 'sides', 'Beer-battered onion rings', 4.49, 1, 410),
    ('DRINK_001', 'Soft Drink', 'drinks', 'Cold soft drink beverage (Medium)', 2.49, 1, 210),
    ('DRINK_002', 'Milkshake', 'drinks', 'Creamy milkshake', 4.99, 1, 520),
    ('DESSERT_001', 'Apple Pie', 'desserts', 'Warm apple pie', 3.99, 1, 320);

-- ============================================================
-- 2. Orders Table
-- ============================================================
CREATE TABLE Orders (
    OrderId UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    CustomerId VARCHAR(50),
    OrderTimestamp DATETIME2 DEFAULT GETUTCDATE(),
    OrderStatus VARCHAR(20) NOT NULL DEFAULT 'pending',
    TotalAmount DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    TaxAmount DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    PaymentMethod VARCHAR(20),
    PaymentStatus VARCHAR(20) DEFAULT 'pending',
    AgentSessionId VARCHAR(100),
    VoiceSessionId VARCHAR(100),
    EstimatedCompletionTime DATETIME2,
    ActualCompletionTime DATETIME2,
    Notes NVARCHAR(MAX),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    UpdatedAt DATETIME2 DEFAULT GETUTCDATE()
);

CREATE INDEX IX_Orders_CustomerId ON Orders(CustomerId);
CREATE INDEX IX_Orders_OrderStatus ON Orders(OrderStatus);
CREATE INDEX IX_Orders_OrderTimestamp ON Orders(OrderTimestamp DESC);
CREATE INDEX IX_Orders_AgentSessionId ON Orders(AgentSessionId);

ALTER TABLE Orders 
ADD CONSTRAINT CK_Orders_Status 
CHECK (OrderStatus IN ('pending', 'confirmed', 'preparing', 'ready', 'completed', 'cancelled'));

-- ============================================================
-- 3. OrderItems Table
-- ============================================================
CREATE TABLE OrderItems (
    OrderItemId UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    OrderId UNIQUEIDENTIFIER NOT NULL,
    MenuItemId VARCHAR(50) NOT NULL,
    ItemName VARCHAR(100) NOT NULL,
    Quantity INT NOT NULL DEFAULT 1,
    UnitPrice DECIMAL(10, 2) NOT NULL,
    Subtotal AS (Quantity * UnitPrice) PERSISTED,
    Customizations NVARCHAR(MAX),
    SpecialInstructions NVARCHAR(500),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    
    CONSTRAINT FK_OrderItems_Orders 
        FOREIGN KEY (OrderId) REFERENCES Orders(OrderId) ON DELETE CASCADE,
    CONSTRAINT FK_OrderItems_Menu 
        FOREIGN KEY (MenuItemId) REFERENCES Menu(MenuItemId),
    CONSTRAINT CK_OrderItems_Quantity 
        CHECK (Quantity > 0)
);

CREATE INDEX IX_OrderItems_OrderId ON OrderItems(OrderId);
CREATE INDEX IX_OrderItems_MenuItemId ON OrderItems(MenuItemId);

-- ============================================================
-- 4. Customers Table (Optional)
-- ============================================================
CREATE TABLE Customers (
    CustomerId VARCHAR(50) PRIMARY KEY,
    FirstName VARCHAR(100),
    LastName VARCHAR(100),
    Email VARCHAR(255),
    PhoneNumber VARCHAR(20),
    PreferredPaymentMethod VARCHAR(20),
    LoyaltyPoints INT DEFAULT 0,
    Preferences NVARCHAR(MAX),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    LastOrderAt DATETIME2
);

CREATE INDEX IX_Customers_Email ON Customers(Email);
CREATE INDEX IX_Customers_PhoneNumber ON Customers(PhoneNumber);
GO

-- ============================================================
-- 5. Analytics View
-- ============================================================
CREATE VIEW OrderAnalytics AS
SELECT 
    CAST(o.OrderTimestamp AS DATE) AS OrderDate,
    DATEPART(HOUR, o.OrderTimestamp) AS OrderHour,
    DATENAME(WEEKDAY, o.OrderTimestamp) AS OrderDayOfWeek,
    
    COUNT(DISTINCT o.OrderId) AS TotalOrders,
    SUM(o.TotalAmount) AS TotalRevenue,
    AVG(o.TotalAmount) AS AvgOrderValue,
    
    oi.MenuItemId,
    oi.ItemName,
    m.Category AS ItemCategory,
    COUNT(*) AS ItemOrderCount,
    SUM(oi.Quantity) AS TotalQuantitySold,
    SUM(oi.Subtotal) AS ItemRevenue
    
FROM Orders o
INNER JOIN OrderItems oi ON o.OrderId = oi.OrderId
INNER JOIN Menu m ON oi.MenuItemId = m.MenuItemId
WHERE o.OrderStatus IN ('completed', 'preparing', 'ready')
GROUP BY 
    CAST(o.OrderTimestamp AS DATE),
    DATEPART(HOUR, o.OrderTimestamp),
    DATENAME(WEEKDAY, o.OrderTimestamp),
    oi.MenuItemId,
    oi.ItemName,
    m.Category;

-- ============================================================
-- Verify schema was created
-- ============================================================
GO

SELECT 'Menu' AS TableName, COUNT(*) AS Row_Count FROM Menu
UNION ALL
SELECT 'Orders' AS TableName, COUNT(*) AS Row_Count FROM Orders
UNION ALL
SELECT 'OrderItems' AS TableName, COUNT(*) AS Row_Count FROM OrderItems
UNION ALL
SELECT 'Customers' AS TableName, COUNT(*) AS Row_Count FROM Customers;
